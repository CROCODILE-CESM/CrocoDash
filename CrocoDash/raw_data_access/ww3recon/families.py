"""
Pluggable frequency shape families for the partition reconstruction.

Each family exposes an unnormalised ``shape(f, fp, param)`` that broadcasts over
``fp`` and ``param``. The reconstructor always renormalises to the archived PHS,
so absolute amplitude conventions are irrelevant here -- only the SHAPE matters.

That renormalisation has a consequence worth stating plainly for the Elfouhaily
family: it is an equilibrium wind-driven model whose amplitude is predicted from
wind speed and wave age. Rescaling it to PHS discards that prediction. What
survives is its spectral shape, parameterised by inverse wave age instead of by
a peak-enhancement factor. That is a defensible use, but it is not "using the
unified spectrum" in the sense Elfouhaily et al. intended.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

G = 9.80665
K_M = 370.0  # capillary peak wavenumber, rad/m (Elfouhaily et al. 1997)
C_M = 0.23  # minimum phase speed, m/s

__all__ = [
    "ShapeFamily",
    "JonswapFamily",
    "PiersonMoskowitzFamily",
    "GaussianFamily",
    "DonelanFamily",
    "OchiHubbleFamily",
    "ElfouhailyFamily",
    "FAMILIES",
    "get_family",
]


@dataclass
class ShapeFamily:
    """Base class. Subclasses implement ``_shape``."""

    name: str = "base"
    param_name: str = "param"
    param_min: float = 0.0
    param_max: float = 1.0
    param_prior: float = 0.5
    n_param: int = 41
    supports_tail_exponent: bool = False
    kind: str = "windsea"  # "windsea", "swell" or "either"

    def param_axis(self) -> np.ndarray:
        return np.linspace(self.param_min, self.param_max, self.n_param)

    def shape(self, f, fp, param, tail_exponent: float = None) -> np.ndarray:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Wind-sea families
# ---------------------------------------------------------------------------


@dataclass
class JonswapFamily(ShapeFamily):
    name: str = "jonswap"
    param_name: str = "gamma"
    param_min: float = 1.0
    param_max: float = 7.0
    param_prior: float = 3.3
    n_param: int = 49
    supports_tail_exponent: bool = True
    kind: str = "windsea"
    sigma_a: float = 0.07
    sigma_b: float = 0.09

    def shape(self, f, fp, gamma, tail_exponent: float = 5.0):
        x = f / fp
        sigma = np.where(f <= fp, self.sigma_a, self.sigma_b)
        r = np.exp(-((f - fp) ** 2) / (2.0 * sigma**2 * fp**2))
        with np.errstate(over="ignore", under="ignore", divide="ignore"):
            base = x ** (-tail_exponent) * np.exp(-1.25 * x**-4.0)
        return base * gamma**r


@dataclass
class PiersonMoskowitzFamily(ShapeFamily):
    """JONSWAP with gamma fixed at 1. Zero shape parameters.

    Included mainly as a null hypothesis: if PM reconstructs as well as fitted
    JONSWAP on your data, the peakedness fit is not earning its complexity.
    """

    name: str = "pierson_moskowitz"
    param_name: str = "unused"
    param_min: float = 1.0
    param_max: float = 1.0
    param_prior: float = 1.0
    n_param: int = 1
    supports_tail_exponent: bool = True
    kind: str = "windsea"

    def shape(self, f, fp, param, tail_exponent: float = 5.0):
        x = f / fp
        with np.errstate(over="ignore", under="ignore", divide="ignore"):
            return x ** (-tail_exponent) * np.exp(-1.25 * x**-4.0)


@dataclass
class DonelanFamily(ShapeFamily):
    """Donelan-Banner-Hasselmann: f^-4 equilibrium range.

    The f^-4 range is better supported observationally for actively growing
    wind sea than Phillips' f^-5, and the peak-width parameter is tied to the
    peak enhancement rather than fixed.
    """

    name: str = "donelan"
    param_name: str = "gamma"
    param_min: float = 1.0
    param_max: float = 7.0
    param_prior: float = 3.3
    n_param: int = 49
    supports_tail_exponent: bool = True
    kind: str = "windsea"

    def shape(self, f, fp, gamma, tail_exponent: float = 4.0):
        x = f / fp
        sigma = 0.08 * (1.0 + 4.0 / np.clip(gamma, 1e-3, None) ** 3)
        r = np.exp(-((f - fp) ** 2) / (2.0 * sigma**2 * fp**2))
        with np.errstate(over="ignore", under="ignore", divide="ignore"):
            base = x ** (-tail_exponent) * np.exp(-(x**-4.0))
        return base * gamma**r


@dataclass
class ElfouhailyFamily(ShapeFamily):
    """Long-wave (gravity) part of the Elfouhaily et al. (1997) unified spectrum,
    mapped from wavenumber to frequency and parameterised by inverse wave age.

    Reference: Elfouhaily, Chapron, Katsaros & Vandemark (1997), JGR 102(C7),
    "A unified directional spectrum for long and short wind-driven waves".

    The curvature spectrum is B(k) = 0.5 alpha_p (c_p/c) F_p with

        F_p    = L_PM * J_p * exp(-Omega_c/sqrt(10) * (sqrt(k/k_p) - 1))
        L_PM   = exp(-1.25 (k_p/k)^2)
        J_p    = gamma^Gamma,  Gamma = exp(-(sqrt(k/k_p)-1)^2 / (2 sigma^2))
        sigma  = 0.08 (1 + 4 / Omega_c^3)
        gamma  = 1.7                      for Omega_c <= 1
               = 1.7 + 6 log10(Omega_c)   for Omega_c >  1
        alpha_p = 0.006 sqrt(Omega_c)

    S(k) = B(k)/k^3, converted with the deep-water Jacobian
    k = (2 pi f)^2 / g, dk/df = 8 pi^2 f / g.

    IMPORTANT SCOPE NOTE. Two things are deliberately dropped here:

    1. The short-wave (capillary) branch B_h. Its peak sits at k_m = 370 rad/m,
       equivalent to ~96 Hz, which is three orders of magnitude above the WW3
       native grid edge of 0.95 Hz. Inside the resolved band it contributes
       nothing. Use ``elfouhaily_tail`` in ``tail.py`` if you need that range.
    2. The absolute amplitude. alpha_p is retained only because it varies with
       Omega_c and therefore slightly changes the shape via the c_p/c factor;
       the reconstructor renormalises to PHS regardless.

    What remains is a JONSWAP-like form whose peak enhancement and width are
    both tied to a single physical parameter (inverse wave age) rather than
    being free. That is arguably better motivated than a free gamma, but within
    the resolved band it is not dramatically different from it -- do not expect
    a large change in reconstruction skill from this family alone.
    """

    name: str = "elfouhaily"
    param_name: str = "omega_c"  # inverse wave age U10 / c_p
    param_min: float = 0.84  # fully developed
    param_max: float = 5.0  # young, strongly forced
    param_prior: float = 1.5
    n_param: int = 45
    supports_tail_exponent: bool = False
    kind: str = "windsea"

    def shape(self, f, fp, omega_c, tail_exponent: float = None):
        omega_c = np.clip(omega_c, 0.84, 5.0)

        k = (2.0 * np.pi * f) ** 2 / G
        kp = (2.0 * np.pi * fp) ** 2 / G

        # Phase speeds including the capillary correction, as in the paper.
        c = np.sqrt(G / k * (1.0 + (k / K_M) ** 2))
        cp = np.sqrt(G / kp * (1.0 + (kp / K_M) ** 2))

        sk = np.sqrt(k / kp)
        L_pm = np.exp(-1.25 * (kp / k) ** 2)
        sigma = 0.08 * (1.0 + 4.0 / omega_c**3)
        Gam = np.exp(-((sk - 1.0) ** 2) / (2.0 * sigma**2))
        gam = np.where(
            omega_c <= 1.0, 1.7, 1.7 + 6.0 * np.log10(np.maximum(omega_c, 1e-3))
        )
        J_p = gam**Gam
        F_p = L_pm * J_p * np.exp(-omega_c / np.sqrt(10.0) * (sk - 1.0))

        alpha_p = 0.006 * np.sqrt(omega_c)
        B_l = 0.5 * alpha_p * (cp / c) * F_p

        S_k = B_l / k**3
        return S_k * (8.0 * np.pi**2 * f / G)  # Jacobian dk/df


# ---------------------------------------------------------------------------
# Swell families
# ---------------------------------------------------------------------------


@dataclass
class GaussianFamily(ShapeFamily):
    name: str = "gaussian"
    param_name: str = "q"
    param_min: float = 0.01
    param_max: float = 0.12
    param_prior: float = 0.04
    n_param: int = 33
    supports_tail_exponent: bool = False
    kind: str = "swell"

    def shape(self, f, fp, q, tail_exponent: float = None):
        return np.exp(-((f - fp) ** 2) / (2.0 * (q * fp) ** 2))


@dataclass
class OchiHubbleFamily(ShapeFamily):
    """Single Ochi-Hubble component with shape parameter lambda.

    More flexible than a Gaussian for swell that retains some asymmetry, and
    unlike the Gaussian it cannot go negative or need clipping at low f. Reduces
    to Bretschneider at lambda = 1.
    """

    name: str = "ochi_hubble"
    param_name: str = "lambda"
    param_min: float = 1.0
    param_max: float = 12.0
    param_prior: float = 3.0
    n_param: int = 45
    supports_tail_exponent: bool = False
    kind: str = "swell"

    def shape(self, f, fp, lam, tail_exponent: float = None):
        # Written in x = f/fp so the powers stay well scaled for large lambda.
        x = f / fp
        a = (4.0 * lam + 1.0) / 4.0
        with np.errstate(over="ignore", under="ignore", divide="ignore"):
            return x ** (-(4.0 * lam + 1.0)) * np.exp(-a * x**-4.0)


FAMILIES = {
    f.name: f
    for f in (
        JonswapFamily(),
        PiersonMoskowitzFamily(),
        DonelanFamily(),
        ElfouhailyFamily(),
        GaussianFamily(),
        OchiHubbleFamily(),
    )
}


def get_family(name_or_family) -> ShapeFamily:
    if isinstance(name_or_family, ShapeFamily):
        return name_or_family
    try:
        return FAMILIES[name_or_family]
    except KeyError:
        raise ValueError(
            f"unknown family {name_or_family!r}; available: {sorted(FAMILIES)}"
        )
