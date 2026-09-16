"""
Reconstruction of 2D wave spectra E(f, theta) from WW3 partition output.

Target dataset: IOWAGA / Ifremer GLOBMULTI_ERA5_GLOBCUR_01.

The reconstruction is deliberately structured so that the expensive part -- the
shape integrals -- depends only on (peak frequency, shape parameter) and can be
tabulated once. Everything downstream is vectorised tensor algebra, so a global
field of ~10^5 points fits in a few chunked array operations rather than 10^5
scipy calls.

See the accompanying hand-off document for the physical rationale, in particular
why m_{-1} (action) constrains peakedness and m_1 (momentum) does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .families import ShapeFamily, get_family

G = 9.80665

__all__ = [
    "SpectralGrid",
    "PartitionSet",
    "ReconstructionConfig",
    "ShapeTables",
    "Reconstructor",
    "moments",
    "bulk_parameters",
    "directional_moments",
]


# ---------------------------------------------------------------------------
# Spectral grid
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpectralGrid:
    """Native WW3 spectral discretisation.

    Defaults are the GLOBMULTI_ERA5_GLOBCUR_01 grid: 36 frequencies from
    0.0339 Hz with a 1.1 geometric ratio, 24 directions at 15 deg (going-to,
    0..345 deg clockwise from N once sorted ascending).

    ``direction_convention`` is carried for bookkeeping only -- this class does
    not reinterpret angles. Confirm the convention empirically against the truth
    spectra before trusting any directional metric (hand-off section 1).
    """

    f: np.ndarray
    theta: np.ndarray  # radians, monotonically increasing over [0, 2pi)
    direction_convention: str = "unspecified"

    @classmethod
    def iowaga(
        cls, n_freq: int = 36, f0: float = 0.0339, ratio: float = 1.1, n_dir: int = 24
    ) -> "SpectralGrid":
        f = f0 * ratio ** np.arange(n_freq)
        theta = np.deg2rad(np.arange(n_dir) * (360.0 / n_dir))
        return cls(f=f, theta=theta)

    @property
    def n_freq(self) -> int:
        return self.f.size

    @property
    def n_dir(self) -> int:
        return self.theta.size

    @property
    def df(self) -> np.ndarray:
        """Frequency bin widths for a geometric ladder.

        For f_i = f_0 r^i the standard WW3 width is df_i = f_i (r - 1/r) / 2,
        which is what the model uses when it integrates its own spectra. Using
        anything else here puts a systematic offset into every moment.
        """
        r = self.f[1] / self.f[0]
        return self.f * (r - 1.0 / r) / 2.0

    @property
    def dtheta(self) -> float:
        return float(self.theta[1] - self.theta[0])


# ---------------------------------------------------------------------------
# Moments and bulk parameters
# ---------------------------------------------------------------------------


def moments(E: np.ndarray, grid: SpectralGrid, orders=(-1, 0, 1, 2)) -> dict:
    """Spectral moments m_n = int int f^n E(f,theta) df dtheta.

    ``E`` has shape (..., n_freq, n_dir) in m^2 s rad^-1.

    Integration is on the native bins. Do not integrate a reconstruction on a
    finer or extended grid and compare it to an archived moment -- the archived
    value is truncated at the native grid edge and the comparison silently
    stops being fair.
    """
    df = grid.df
    dth = grid.dtheta
    Ef = E.sum(axis=-1) * dth  # (..., n_freq) -> 1D frequency spectrum
    out = {}
    for n in orders:
        out[n] = np.einsum("...i,i->...", Ef, grid.f**n * df)
    return out


def bulk_parameters(E: np.ndarray, grid: SpectralGrid) -> dict:
    """Hs, Tm-10, Tm01, Tm02, plus action and momentum proxies."""
    m = moments(E, grid, orders=(-1, 0, 1, 2))
    m0 = m[0]
    with np.errstate(divide="ignore", invalid="ignore"):
        return {
            "hs": 4.0 * np.sqrt(np.maximum(m0, 0.0)),
            "tm10": m[-1] / m0,
            "tm01": m0 / m[1],
            "tm02": np.sqrt(m0 / m[2]),
            "m0": m0,
            "m_minus1": m[-1],
            "m1": m[1],
            "m2": m[2],
            # Deep water, per unit area, divided through by rho.
            "energy_over_rho": G * m0,
            "action_over_rho": G * m[-1] / (2.0 * np.pi),
            "momentum_over_rho": 2.0 * np.pi * m[1],
        }


def directional_moments(E: np.ndarray, grid: SpectralGrid) -> dict:
    """Directional Fourier coefficients a1,b1,a2,b2 as functions of frequency.

    This is the most diagnostic comparison against the truth spectra: a2/b2
    exposes a wrong directional family in a way that Hs and period never will.
    """
    th = grid.theta
    dth = grid.dtheta
    c1, s1 = np.cos(th), np.sin(th)
    c2, s2 = np.cos(2 * th), np.sin(2 * th)
    e = E.sum(axis=-1) * dth
    with np.errstate(divide="ignore", invalid="ignore"):
        return {
            "e": e,
            "a1": (E @ c1) * dth / e,
            "b1": (E @ s1) * dth / e,
            "a2": (E @ c2) * dth / e,
            "b2": (E @ s2) * dth / e,
        }


# ---------------------------------------------------------------------------
# Shape functions
# ---------------------------------------------------------------------------


def jonswap_shape(f, fp, gamma, tail_exponent: float = 5.0):
    """Thin wrapper kept for convenience; see families.JonswapFamily."""
    return get_family("jonswap").shape(f, fp, gamma, tail_exponent=tail_exponent)


def gaussian_shape(f, fp, q):
    """Thin wrapper kept for convenience; see families.GaussianFamily."""
    return get_family("gaussian").shape(f, fp, q)


def spread_to_s(
    spread_rad: np.ndarray, s_min: float = 0.5, s_max: float = 200.0
) -> np.ndarray:
    """Kuik circular spread -> cos-2s exponent.

    For cos^{2s}((theta-thetabar)/2) the first directional moment ratio is
    s/(s+1), and sigma_theta = sqrt(2(1 - <cos>)), giving sigma^2 = 2/(s+1).

    If this run turns out to define PSPR from the SECOND directional
    coefficients instead, this mapping is wrong -- see ``check_spread_convention``.
    """
    sp = np.asarray(spread_rad, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        s = 2.0 / np.maximum(sp, 1e-6) ** 2 - 1.0
    return np.clip(s, s_min, s_max)


def cos2s(
    theta: np.ndarray, theta_bar: np.ndarray, s: np.ndarray, dtheta: float
) -> np.ndarray:
    """Normalised cos-2s directional distribution, integrating to 1 in theta.

    Normalisation is done numerically on the native direction bins rather than
    via the analytic Gamma-function constant, so that int D dtheta is exactly 1
    on the discrete grid. That matters: with 24 bins the analytic constant
    leaves a percent-level energy error for narrow swell.

    ``dtheta`` is required explicitly rather than inferred from ``theta``, which
    is usually passed broadcast to rank 3 -- inferring it silently drops the bin
    width and inflates every spectrum by 1/dtheta.
    """
    # Wrap the angular difference to (-pi, pi] BEFORE halving. Without this,
    # a partition at 330 deg sees theta = 0 deg as a -330 deg offset, cos(-165)
    # is negative and gets clipped to zero, and the whole sector across the
    # 0/360 seam is empty. That was the "directional zero-wedge" in the first
    # real-data run -- an indexing bug, not a property of cos-2s, which is
    # zero only at the single direction 180 deg from the partition.
    dphi = np.angle(np.exp(1j * (theta - theta_bar)))
    d = np.cos(0.5 * dphi)
    d = np.where(d > 0, d, 0.0)
    with np.errstate(over="ignore", under="ignore"):
        D = d ** (2.0 * s)
    norm = D.sum(axis=-1, keepdims=True) * dtheta
    return np.divide(
        D, np.where(norm > 0, norm, 1.0), out=np.zeros_like(D), where=norm > 0
    )


# ---------------------------------------------------------------------------
# Precomputed shape tables
# ---------------------------------------------------------------------------


@dataclass
class ShapeTables:
    """Tabulated normalised moment ratios for each shape family.

    The key structural point: for a frequency shape normalised to unit m0, the
    ratios m_{-1}/m0 and m2/m0 depend only on (fp, shape parameter). Truncation
    at the grid edge breaks exact self-similarity in fp, so fp is tabulated
    explicitly rather than scaled out.

    That turns the per-point fit from a nonlinear optimisation into a table
    lookup plus vectorised arithmetic, for ANY family -- adding a family costs
    only its table build, not a new solver.
    """

    grid: SpectralGrid
    ws_family: ShapeFamily
    sw_family: ShapeFamily
    fp_axis: np.ndarray
    ws_axis: np.ndarray
    sw_axis: np.ndarray
    tail_axis: np.ndarray
    r_ws: np.ndarray = field(repr=False, default=None)  # (n_tail, n_fp, n_ws)
    s_ws: np.ndarray = field(repr=False, default=None)
    r_sw: np.ndarray = field(repr=False, default=None)  # (n_fp, n_sw)
    s_sw: np.ndarray = field(repr=False, default=None)

    @classmethod
    def build(
        cls,
        grid: SpectralGrid,
        ws_family="elfouhaily",
        sw_family="ochi_hubble",
        n_fp: int = 96,
        tail_axis=(3.5, 4.0, 4.5, 5.0, 5.5, 6.0),
    ) -> "ShapeTables":
        ws = get_family(ws_family)
        sw = get_family(sw_family)
        f, df = grid.f, grid.df
        fp_axis = np.geomspace(f[0], f[-1] / 2.0, n_fp)
        ws_axis = ws.param_axis()
        sw_axis = sw.param_axis()

        # Families with an intrinsic tail (e.g. Elfouhaily) get a single slot:
        # their high-frequency slope is set by the physics, not fitted.
        tail_axis = (
            np.asarray(tail_axis, float)
            if ws.supports_tail_exponent
            else np.array([np.nan])
        )

        FP = fp_axis[:, None, None]
        F = f[None, None, :]

        PW = ws_axis[None, :, None]
        r_ws = np.empty((tail_axis.size, fp_axis.size, ws_axis.size))
        s_ws = np.empty_like(r_ws)
        for it, n in enumerate(tail_axis):
            kw = {} if np.isnan(n) else {"tail_exponent": float(n)}
            S = np.nan_to_num(ws.shape(F, FP, PW, **kw))
            m0 = np.einsum("fgk,k->fg", S, df)
            m0 = np.where(m0 > 0, m0, np.nan)
            r_ws[it] = np.einsum("fgk,k->fg", S, df / f) / m0
            s_ws[it] = np.einsum("fgk,k->fg", S, df * f**2) / m0

        PS = sw_axis[None, :, None]
        S = np.nan_to_num(sw.shape(F, FP, PS))
        m0 = np.einsum("fqk,k->fq", S, df)
        m0 = np.where(m0 > 0, m0, np.nan)
        r_sw = np.einsum("fqk,k->fq", S, df / f) / m0
        s_sw = np.einsum("fqk,k->fq", S, df * f**2) / m0

        return cls(
            grid=grid,
            ws_family=ws,
            sw_family=sw,
            fp_axis=fp_axis,
            ws_axis=ws_axis,
            sw_axis=sw_axis,
            tail_axis=tail_axis,
            r_ws=r_ws,
            s_ws=s_ws,
            r_sw=r_sw,
            s_sw=s_sw,
        )

    def _interp_fp(self, table: np.ndarray, fp: np.ndarray) -> np.ndarray:
        idx = np.clip(np.searchsorted(self.fp_axis, fp) - 1, 0, self.fp_axis.size - 2)
        f0, f1 = self.fp_axis[idx], self.fp_axis[idx + 1]
        w = ((fp - f0) / (f1 - f0))[..., None]
        return table[idx] * (1 - w) + table[idx + 1] * w

    def ratios_ws(self, fp, tail_index: int):
        return (
            self._interp_fp(self.r_ws[tail_index], fp),
            self._interp_fp(self.s_ws[tail_index], fp),
        )

    def ratios_sw(self, fp):
        return self._interp_fp(self.r_sw, fp), self._interp_fp(self.s_sw, fp)


# ---------------------------------------------------------------------------
# Inputs and config
# ---------------------------------------------------------------------------


@dataclass
class PartitionSet:
    """Per-partition inputs, all shaped (n_points, n_partitions).

    Inactive partitions are marked by NaN in ``phs`` (or zero height).
    Directions and spread are in DEGREES on input, matching the archive.
    """

    phs: np.ndarray
    ptp: np.ndarray
    pdir: np.ndarray
    pspr: np.ndarray
    pws: np.ndarray
    # whole-spectrum fields, shaped (n_points,)
    hs: np.ndarray = None
    t0m1: np.ndarray = None
    t02: np.ndarray = None

    def __post_init__(self):
        self.phs = np.atleast_2d(np.asarray(self.phs, float))
        self.ptp = np.atleast_2d(np.asarray(self.ptp, float))
        self.pdir = np.atleast_2d(np.asarray(self.pdir, float))
        self.pspr = np.atleast_2d(np.asarray(self.pspr, float))
        self.pws = np.atleast_2d(np.asarray(self.pws, float))
        for name in ("hs", "t0m1", "t02"):
            v = getattr(self, name)
            if v is not None:
                setattr(self, name, np.atleast_1d(np.asarray(v, float)))

    @property
    def n_points(self) -> int:
        return self.phs.shape[0]

    @property
    def n_partitions(self) -> int:
        return self.phs.shape[1]

    @property
    def active(self) -> np.ndarray:
        return np.isfinite(self.phs) & (self.phs > 1e-4) & np.isfinite(self.ptp)

    @property
    def m0(self) -> np.ndarray:
        """Per-partition zeroth moment, zero where inactive."""
        return np.where(self.active, np.nan_to_num(self.phs) ** 2 / 16.0, 0.0)


@dataclass
class ReconstructionConfig:
    # Shape families. Wind sea: "jonswap", "donelan", "elfouhaily",
    # "pierson_moskowitz". Swell: "gaussian", "ochi_hubble".
    # Defaults are the best combination on four IOWAGA sites, Jan 1993
    # (HANDOFF section 4): Elfouhaily wind sea + Ochi-Hubble swell. The swell
    # choice is the one that matters (~0.2 in spectral correlation); the four
    # wind-sea families are within 0.004 of each other.
    windsea_family: str = "elfouhaily"
    swell_family: str = "ochi_hubble"

    ws_threshold: float = 0.7  # PWS above this -> pure wind sea
    sw_threshold: float = 0.3  # PWS below this -> pure swell

    # Prior weights. The penalty is on the parameter normalised by its own
    # range, so these are dimensionless and comparable across families -- you
    # do not need to retune them when swapping JONSWAP for Elfouhaily.
    lambda_ws: float = 0.7
    lambda_sw: float = 0.7
    # Override the family default prior if you want; None uses the family's.
    ws_prior: float = None
    sw_prior: float = None

    epsilon_t0m1: float = 0.01  # relative tolerance on Tm-10
    fit_tail: bool = True
    n_outer_iterations: int = 2
    closure_warn: float = 0.95
    chunk_size: int = 20000


# ---------------------------------------------------------------------------
# Reconstructor
# ---------------------------------------------------------------------------


class Reconstructor:
    """Reconstruct E(f, theta) from partition bulk parameters.

    Usage
    -----
    >>> grid = SpectralGrid.iowaga()
    >>> rec = Reconstructor(grid)
    >>> result = rec.reconstruct(partitions)
    >>> E = result["spectrum"]           # (n_points, n_freq, n_dir)
    """

    def __init__(
        self,
        grid: SpectralGrid = None,
        config: ReconstructionConfig = None,
        tables: ShapeTables = None,
    ):
        self.grid = grid or SpectralGrid.iowaga()
        self.config = config or ReconstructionConfig()
        self.tables = tables or ShapeTables.build(
            self.grid,
            ws_family=self.config.windsea_family,
            sw_family=self.config.swell_family,
        )
        self.ws_family = self.tables.ws_family
        self.sw_family = self.tables.sw_family

    # -- stage 1: peakedness from the action moment ---------------------------

    def _fit_shape(self, p: PartitionSet, tail_index: int):
        """Solve for (gamma_ws, q_sw) by matching the archived Tm-10.

        m_{-1} is linear in the partition energies, so with the shape ratios
        tabulated this reduces to a vectorised grid search over two scalars
        rather than a per-point optimiser call.

        Only ONE constraint is available for TWO unknowns, which is why the
        priors are load-bearing here rather than cosmetic. Where a point has
        only one family present the constraint is exactly determined and the
        prior on the absent family is irrelevant.
        """
        cfg = self.config
        m0 = p.m0  # (np, npart)
        fp = np.where(p.active, 1.0 / np.where(p.ptp > 0, p.ptp, np.nan), 0.0)
        fp = np.nan_to_num(fp)
        fp_c = np.clip(fp, self.tables.fp_axis[0], self.tables.fp_axis[-1])

        w_ws = np.clip(
            (p.pws - cfg.sw_threshold) / (cfg.ws_threshold - cfg.sw_threshold), 0.0, 1.0
        )
        w_ws = np.where(p.active, np.nan_to_num(w_ws), 0.0)
        w_sw = np.where(p.active, 1.0 - w_ws, 0.0)

        r_ws, _ = self.tables.ratios_ws(fp_c, tail_index)  # (np, npart, n_ws)
        r_sw, _ = self.tables.ratios_sw(fp_c)  # (np, npart, n_sw)

        # Energy-weighted contributions to m_{-1} from each family.
        A_ws = np.einsum("pk,pkg->pg", m0 * w_ws, np.nan_to_num(r_ws))
        A_sw = np.einsum("pk,pkq->pq", m0 * w_sw, np.nan_to_num(r_sw))

        m0_tot = m0.sum(axis=1)
        # Match the RATIO Tm-10, not the absolute moment: this decouples the
        # shape fit from partition-truncation closure error.
        target = np.where(m0_tot > 0, p.t0m1 * m0_tot, np.nan)

        ga = self.tables.ws_axis
        qa = self.tables.sw_axis
        wsf, swf = self.ws_family, self.sw_family
        p_ws = cfg.ws_prior if cfg.ws_prior is not None else wsf.param_prior
        p_sw = cfg.sw_prior if cfg.sw_prior is not None else swf.param_prior
        # Normalise by the parameter's own range so the weight is dimensionless.
        rng_ws = max(wsf.param_max - wsf.param_min, 1e-9)
        rng_sw = max(swf.param_max - swf.param_min, 1e-9)
        pen_g = cfg.lambda_ws * ((ga - p_ws) / rng_ws) ** 2
        pen_q = cfg.lambda_sw * ((qa - p_sw) / rng_sw) ** 2

        # The search grid is float32 and built in place: it is (n_points x
        # n_gamma x n_q) and dominates runtime otherwise. Single precision is
        # ample for locating an argmin on a discretised grid -- the fitted
        # gamma is only resolved to the grid spacing regardless.
        scale = (np.maximum(np.abs(target), 1e-9) * cfg.epsilon_t0m1).astype(np.float32)
        aw = (A_ws / scale[:, None]).astype(np.float32)
        aq = (A_sw / scale[:, None]).astype(np.float32)
        tg = (target / scale).astype(np.float32)

        obj = aw[:, :, None] + aq[:, None, :]
        obj -= tg[:, None, None]
        obj *= obj
        obj += pen_g.astype(np.float32)[None, :, None]
        obj += pen_q.astype(np.float32)[None, None, :]
        np.nan_to_num(obj, copy=False, nan=np.inf, posinf=np.inf)

        flat = obj.reshape(obj.shape[0], -1).argmin(axis=1)
        ig, iq = np.unravel_index(flat, (ga.size, qa.size))
        gamma = ga[ig]
        q = qa[iq]

        best = obj.reshape(obj.shape[0], -1)[np.arange(obj.shape[0]), flat]
        # A point is under-constrained for a family it does not contain.
        has_ws = (m0 * w_ws).sum(axis=1) > 1e-8 * np.maximum(m0_tot, 1e-12)
        has_sw = (m0 * w_sw).sum(axis=1) > 1e-8 * np.maximum(m0_tot, 1e-12)

        return {
            "gamma": gamma,
            "q": q,
            "ig": ig,
            "iq": iq,
            "fit_residual": best,
            "w_ws": w_ws,
            "w_sw": w_sw,
            "fp": fp_c,
            "m0": m0,
            "underconstrained_ws": ~has_ws,
            "underconstrained_sw": ~has_sw,
        }

    # -- stage 2: tail exponent from Tm02 -------------------------------------

    def _fit_tail(self, p: PartitionSet, st: dict) -> np.ndarray:
        """Pick the wind-sea tail exponent that best matches archived Tm02.

        m2 is tail-dominated, so this is the moment that carries information
        about the high-frequency slope. It says almost nothing about the peak
        shape, which is why it is a separate stage.

        Families with an intrinsic tail (Elfouhaily) have nothing to fit: their
        slope follows from the physics. This returns index 0 for those.
        """
        if not self.ws_family.supports_tail_exponent:
            return np.zeros(p.n_points, int)

        m0, fp = st["m0"], st["fp"]
        m0_tot = m0.sum(axis=1)
        target_m2 = np.where(m0_tot > 0, m0_tot / np.maximum(p.t02, 1e-6) ** 2, np.nan)

        _, s_sw = self.tables.ratios_sw(fp)
        iq = st["iq"]
        m2_sw = np.einsum(
            "pk,pk->p",
            m0 * st["w_sw"],
            np.nan_to_num(np.take_along_axis(s_sw, iq[:, None, None], axis=2)[:, :, 0]),
        )

        ig = st["ig"]
        errs = []
        for it in range(self.tables.tail_axis.size):
            _, s_ws = self.tables.ratios_ws(fp, it)
            m2_ws = np.einsum(
                "pk,pk->p",
                m0 * st["w_ws"],
                np.nan_to_num(
                    np.take_along_axis(s_ws, ig[:, None, None], axis=2)[:, :, 0]
                ),
            )
            errs.append(np.abs(m2_ws + m2_sw - target_m2))
        errs = np.stack(errs, axis=0)
        errs = np.where(np.isfinite(errs), errs, np.inf)
        return errs.argmin(axis=0)

    # -- assembly -------------------------------------------------------------

    def _assemble(self, p: PartitionSet, st: dict, tail_idx: np.ndarray) -> np.ndarray:
        grid = self.grid
        f = grid.f[None, None, :]
        df = grid.df
        fp = st["fp"][:, :, None]
        ws_p = st["gamma"][:, None, None]
        sw_p = st["q"][:, None, None]

        S_sw = np.nan_to_num(self.sw_family.shape(f, fp, sw_p))
        S_sw /= np.maximum((S_sw * df).sum(axis=-1, keepdims=True), 1e-30)

        S_ws = np.zeros_like(S_sw)
        for it in np.unique(tail_idx):
            sel = tail_idx == it
            if not sel.any():
                continue
            tail = self.tables.tail_axis[it]
            kw = {} if np.isnan(tail) else {"tail_exponent": float(tail)}
            sh = np.nan_to_num(self.ws_family.shape(f, fp[sel], ws_p[sel], **kw))
            sh /= np.maximum((sh * df).sum(axis=-1, keepdims=True), 1e-30)
            S_ws[sel] = sh

        # Blending the NORMALISED shapes (rather than hard switching on PWS)
        # avoids discontinuities in time series where PWS crosses the threshold.
        Ef = st["m0"][:, :, None] * (
            st["w_ws"][:, :, None] * S_ws + st["w_sw"][:, :, None] * S_sw
        )

        s_exp = spread_to_s(np.deg2rad(np.nan_to_num(p.pspr)))
        D = cos2s(
            grid.theta[None, None, :],
            np.deg2rad(np.nan_to_num(p.pdir))[:, :, None],
            s_exp[:, :, None],
            grid.dtheta,
        )

        # Additive superposition -- label-invariant, so partition index swapping
        # between neighbouring cells is harmless by construction.
        return np.einsum("pkf,pkt->pft", Ef, D)

    # -- public API -----------------------------------------------------------

    def reconstruct(self, p: PartitionSet) -> dict:
        """Reconstruct spectra for all points in ``p``.

        Returns a dict with ``spectrum`` (n_points, n_freq, n_dir) plus the
        fitted parameters and the diagnostics needed to filter downstream.
        """
        if p.t0m1 is None:
            raise ValueError("t0m1 (archived Tm-10) is required for the shape fit")

        cfg = self.config
        n = p.n_points
        out_E = np.zeros((n, self.grid.n_freq, self.grid.n_dir))
        diag = {
            k: np.zeros(n)
            for k in (
                "ws_param",
                "sw_param",
                "fit_residual",
                "tail_exponent",
                "energy_closure",
                "n_partitions",
            )
        }
        flags = {
            k: np.zeros(n, bool)
            for k in ("underconstrained_ws", "underconstrained_sw", "low_closure")
        }

        for lo in range(0, n, cfg.chunk_size):
            hi = min(lo + cfg.chunk_size, n)
            sl = slice(lo, hi)
            chunk = PartitionSet(
                phs=p.phs[sl],
                ptp=p.ptp[sl],
                pdir=p.pdir[sl],
                pspr=p.pspr[sl],
                pws=p.pws[sl],
                hs=None if p.hs is None else p.hs[sl],
                t0m1=p.t0m1[sl],
                t02=None if p.t02 is None else p.t02[sl],
            )

            ta = self.tables.tail_axis
            tail_idx = (
                np.zeros(hi - lo, int)
                if np.isnan(ta[0])
                else np.full(hi - lo, int(np.argmin(np.abs(ta - 5.0))))
            )
            st = None
            for _ in range(cfg.n_outer_iterations if cfg.fit_tail else 1):
                st = self._fit_shape(
                    chunk, tail_index=int(np.bincount(tail_idx).argmax())
                )
                if cfg.fit_tail and chunk.t02 is not None:
                    tail_idx = self._fit_tail(chunk, st)
                else:
                    break

            out_E[sl] = self._assemble(chunk, st, tail_idx)

            diag["ws_param"][sl] = st["gamma"]
            diag["sw_param"][sl] = st["q"]
            diag["fit_residual"][sl] = st["fit_residual"]
            diag["tail_exponent"][sl] = self.tables.tail_axis[tail_idx]
            diag["n_partitions"][sl] = chunk.active.sum(axis=1)
            flags["underconstrained_ws"][sl] = st["underconstrained_ws"]
            flags["underconstrained_sw"][sl] = st["underconstrained_sw"]

            if chunk.hs is not None:
                closure = np.divide(
                    (np.nan_to_num(chunk.phs) ** 2).sum(axis=1),
                    np.maximum(chunk.hs**2, 1e-12),
                )
                diag["energy_closure"][sl] = closure
                flags["low_closure"][sl] = closure < cfg.closure_warn

        return {
            "spectrum": out_E,
            "grid": self.grid,
            "ws_family": self.ws_family.name,
            "sw_family": self.sw_family.name,
            "ws_param_name": self.ws_family.param_name,
            "sw_param_name": self.sw_family.param_name,
            **diag,
            **flags,
        }
