"""Tests for the IOWAGA GLOBMULTI_ERA5_GLOBCUR_01 partition-spectra product.

Everything except the one `slow`-marked test is offline. The reconstruction
(`spectra_from_partitions`) and the window selection are pure, so they run
against a fabricated dataset shaped like a real monthly file; the coverage
check reaches the network only through `available_months`, which is
monkeypatched here.

The two things most likely to break silently are covered directly: the
per-partition renormalization (each partition must come back at exactly its
own phs) and the directional normalization (which is what makes that true).
"""

import numpy as np
import pytest
import xarray as xr

from CrocoDash.raw_data_access.datasets import iowaga
from CrocoDash.raw_data_access.datasets.iowaga import (
    DEFAULT_N_DIRECTIONS,
    N_PARTITIONS,
    IOWAGA,
    DEFAULT_POINT_BLOCK,
    T0M1_FIELD,
    T02_FIELD,
    build_month_url,
    check_coverage,
    iowaga_frequencies,
    iowaga_spectral_grid,
    months_in_range,
    partition_variable_names,
    significant_height_from_efth,
    spectra_from_partitions,
    verify_hs_against_source,
    _select_window,
)

# --------------------------------------------------------------------------
# Fabricated monthly window
# --------------------------------------------------------------------------


def make_window(
    n_time=3,
    n_lat=4,
    n_lon=5,
    partitions=((2.0, 12.0, 210.0, 25.0),),
    lon_start=-33.0,
    lat_ascending=True,
    hs=None,
    t0m1=None,
    t02=None,
    drop=(),
):
    """A window shaped like a real IOWAGA monthly file, restricted to a box.

    `partitions` is a tuple of (phs, ptp, pdir, pspr) or
    (phs, ptp, pdir, pspr, pws) per partition; absent partitions are written
    as NaN, matching how the real files mark them. `pws` defaults the way the
    archive orders them -- partition 0 is the wind sea, 1-5 are swell.

    `hs` defaults to the energy-complete total, sqrt(sum phs_i^2), which is
    what the real files carry. `t0m1` and `t02` default to energy-weighted
    values consistent with the partitions, so the per-point shape fit has a
    solvable constraint rather than one it has to rail against a bound to
    satisfy; `drop` removes variables to exercise the missing-field paths.
    """
    shape = (n_time, n_lat, n_lon)
    dims = ("time", "latitude", "longitude")
    data = {}
    for index in range(N_PARTITIONS):
        if index < len(partitions):
            values = list(partitions[index])
            if len(values) == 4:
                values.append(1.0 if index == 0 else 0.0)
            phs, ptp, pdir, pspr, pws = values
        else:
            phs = ptp = pdir = pspr = pws = np.nan
        for field, value in zip(
            ("phs", "ptp", "pdir", "pspr", "pws"), (phs, ptp, pdir, pspr, pws)
        ):
            data[f"{field}{index}"] = (dims, np.full(shape, value, dtype=np.float64))

    m0 = np.array([p[0] ** 2 for p in partitions], dtype=np.float64)
    tp = np.array([p[1] for p in partitions], dtype=np.float64)
    if hs is None:
        hs = float(np.sqrt(m0.sum()))
    # Tm-10 ~ 0.9 Tp and Tm02 ~ 0.75 Tp for a JONSWAP-like shape; combined
    # across partitions by energy, which is how the moments actually add.
    if t0m1 is None:
        t0m1 = float((m0 * 0.90 * tp).sum() / m0.sum())
    if t02 is None:
        t02 = float((m0 * 0.75 * tp).sum() / m0.sum())
    data["hs"] = (dims, np.full(shape, hs, dtype=np.float64))
    data[T0M1_FIELD] = (dims, np.full(shape, t0m1, dtype=np.float64))
    data[T02_FIELD] = (dims, np.full(shape, t02, dtype=np.float64))
    for name in drop:
        data.pop(name, None)

    lat = np.linspace(47.0, 47.0 + 0.5 * (n_lat - 1), n_lat)
    if not lat_ascending:
        lat = lat[::-1]

    return xr.Dataset(
        data,
        coords={
            "time": np.array(
                ["2020-01-01T00", "2020-01-01T03", "2020-01-01T06"],
                dtype="datetime64[ns]",
            )[:n_time],
            "latitude": lat,
            "longitude": lon_start + 0.5 * np.arange(n_lon),
        },
    )


def hs_from_efth(ds):
    return significant_height_from_efth(
        ds["efth"].values,
        iowaga_spectral_grid(
            frequency=ds["frequency"].values, direction=ds["direction"].values
        ),
    )


# --------------------------------------------------------------------------
# reconstruction
# --------------------------------------------------------------------------


def test_output_has_exactly_one_variable():
    """forcing/ww3.py::_extract_all_stations does `(var_name,) = ds.data_vars`."""
    out = spectra_from_partitions(make_window())
    assert list(out.data_vars) == ["efth"]


def test_output_dims_match_the_ww3_contract():
    out = spectra_from_partitions(make_window())
    assert out["efth"].dims == (
        "time",
        "latitude",
        "longitude",
        "frequency",
        "direction",
    )
    assert out.sizes["frequency"] == 36
    assert out.sizes["direction"] == DEFAULT_N_DIRECTIONS


def test_single_partition_reproduces_its_own_significant_height():
    """The per-partition renormalization is the core of the reconstruction."""
    out = spectra_from_partitions(make_window(partitions=((3.25, 11.0, 180.0, 20.0),)))
    assert np.allclose(hs_from_efth(out), 3.25, rtol=2e-3)


def test_partitions_combine_in_quadrature():
    """Independent systems add in energy, so total Hs = sqrt(sum phs_i^2)."""
    partitions = (
        (2.0, 8.0, 270.0, 30.0),
        (1.5, 14.0, 200.0, 18.0),
        (1.0, 18.0, 120.0, 12.0),
    )
    out = spectra_from_partitions(make_window(partitions=partitions))
    expected = np.sqrt(sum(p[0] ** 2 for p in partitions))
    assert np.allclose(hs_from_efth(out), expected, rtol=3e-3)


@pytest.mark.parametrize("n_directions", [12, 24, 36])
def test_hs_is_independent_of_direction_count(n_directions):
    """Numerical rather than analytic normalization means directional
    resolution must not change the total energy."""
    out = spectra_from_partitions(
        make_window(partitions=((2.5, 10.0, 90.0, 25.0),)), n_directions=n_directions
    )
    assert np.allclose(hs_from_efth(out), 2.5, rtol=3e-3)


def test_absent_partitions_are_skipped_not_counted():
    """Only partition 0 is present; the NaN ones must contribute nothing."""
    out = spectra_from_partitions(make_window(partitions=((2.0, 12.0, 210.0, 25.0),)))
    assert np.isfinite(out["efth"].values).all()
    assert np.allclose(hs_from_efth(out), 2.0, rtol=2e-3)


def test_crossing_sea_keeps_two_distinct_lobes():
    """Six partitions are the reason to prefer this over the ERA5 route."""
    out = spectra_from_partitions(
        make_window(
            partitions=((2.0, 7.0, 0.0, 15.0), (2.0, 16.0, 180.0, 15.0)),
        ),
        n_directions=24,
    )
    energy = out["efth"].isel(time=0, latitude=0, longitude=0).sum("frequency").values
    directions = out["direction"].values
    assert np.isclose(directions[int(np.argmax(energy))] % 180.0, 0.0)
    # Energy at both 0 and 180 degrees, and a trough between them.
    at_0 = energy[int(np.where(directions == 0.0)[0][0])]
    at_180 = energy[int(np.where(directions == 180.0)[0][0])]
    at_90 = energy[int(np.where(directions == 90.0)[0][0])]
    assert at_0 > 10 * at_90 and at_180 > 10 * at_90


def test_lobe_is_centred_on_pdir_unrotated():
    """Pins the direction convention.

    `pdir` is sea_surface_wave_from_direction_partition_N and
    write_ww3_boundary_spectrum wants the same "coming from" convention, so
    the lobe sits ON pdir. Verified against real data (see module docstring);
    note IOWAGA's own point spectra use a to-direction axis, so a naive
    comparison against those looks exactly backwards.
    """
    out = spectra_from_partitions(make_window(partitions=((2.0, 12.0, 210.0, 20.0),)))
    energy = out["efth"].isel(time=0, latitude=0, longitude=0).sum("frequency")
    peak = float(out["direction"].values[int(np.argmax(energy.values))])
    assert peak == 210.0, f"lobe peaked at {peak}, expected 210 (coming-from)"


def test_output_direction_axis_documents_the_convention():
    out = spectra_from_partitions(make_window())
    assert "coming FROM" in out["direction"].attrs.get("comment", "")


def test_reconstruction_raises_without_any_partition():
    window = make_window().drop_vars(
        [
            f"{f}{i}"
            for f in ("phs", "ptp", "pdir", "pspr", "pws")
            for i in range(N_PARTITIONS)
        ]
    )
    with pytest.raises(KeyError, match="No complete partition"):
        spectra_from_partitions(window)


def test_hs_self_check_catches_lost_energy():
    """A window whose `hs` implies more energy than the partitions carry --
    the signature of a mis-indexed or dropped partition."""
    window = make_window(partitions=((2.0, 12.0, 210.0, 25.0),), hs=6.0)
    with pytest.raises(ValueError, match="self-check"):
        spectra_from_partitions(window)


def test_hs_self_check_records_diagnostics():
    out = spectra_from_partitions(make_window())
    assert out["efth"].attrs["hs_check"] == "passed"
    assert out["efth"].attrs["hs_check_n_points"] > 0
    assert out["efth"].attrs["residual_system_synthesized"].startswith("no")


def test_hs_self_check_can_be_skipped():
    out = spectra_from_partitions(make_window().drop_vars("hs"))
    assert "skipped" in out["efth"].attrs["hs_check"]


def test_verify_hs_passes_on_a_faithful_reconstruction():
    out = spectra_from_partitions(make_window(partitions=((2.0, 12.0, 210.0, 25.0),)))
    diagnostics = verify_hs_against_source(
        out["efth"].values,
        iowaga_spectral_grid(),
        np.full(out["efth"].shape[:3], 2.0),
    )
    assert diagnostics["hs_check"] == "passed"


# --------------------------------------------------------------------------
# the fitted shape
# --------------------------------------------------------------------------


def test_t0m1_is_required():
    """It is the only constraint the shape fit is solved against."""
    with pytest.raises(KeyError, match="not optional"):
        spectra_from_partitions(make_window(drop=(T0M1_FIELD,)))


def test_peakedness_responds_to_the_archived_t0m1():
    """The point of fitting rather than assuming a shape.

    Same partitions, different archived Tm-10: the reconstruction must come
    back with a different spectral shape and the SAME significant height,
    because Hs is set by renormalization and the shape by the fit.
    """
    partitions = ((3.0, 12.0, 210.0, 25.0),)
    peaked = spectra_from_partitions(make_window(partitions=partitions, t0m1=9.5))
    broad = spectra_from_partitions(make_window(partitions=partitions, t0m1=11.5))

    assert np.allclose(hs_from_efth(peaked), hs_from_efth(broad), rtol=3e-3)
    assert not np.allclose(
        peaked["efth"].values, broad["efth"].values, rtol=1e-2, atol=1e-6
    )


def test_wind_sea_fraction_selects_the_frequency_family():
    """`pws` blends the two families, so it has to change the shape."""
    windsea = spectra_from_partitions(
        make_window(partitions=((2.5, 10.0, 180.0, 25.0, 1.0),))
    )
    swell = spectra_from_partitions(
        make_window(partitions=((2.5, 10.0, 180.0, 25.0, 0.0),))
    )
    assert np.allclose(hs_from_efth(windsea), hs_from_efth(swell), rtol=3e-3)
    assert not np.allclose(
        windsea["efth"].values, swell["efth"].values, rtol=1e-2, atol=1e-6
    )
    assert windsea["efth"].attrs["windsea_family"] == "elfouhaily"
    assert swell["efth"].attrs["swell_family"] == "ochi_hubble"


def test_masked_points_are_skipped_not_fitted():
    """Land and ice carry NaN moments; a NaN constraint has no solution.

    Those points must come back as exact zeros and must not enter the fit --
    letting one through would poison the chunk-modal tail exponent that the
    wet points in the same block share.
    """
    window = make_window(n_time=2, n_lat=2, n_lon=3)
    for name in (T0M1_FIELD, T02_FIELD, "hs"):
        masked = window[name].values.copy()
        masked[:, 0, :] = np.nan
        window[name] = (window[name].dims, masked)

    out = spectra_from_partitions(window)
    efth = out["efth"].values
    assert np.all(efth[:, 0, :] == 0.0)
    # Per-bin, not every bin: far from the lobe the density underflows to an
    # honest zero in float32. It is the total energy that has to be there.
    assert np.all(efth[:, 1, :].sum(axis=(-2, -1)) > 0.0)
    assert np.isfinite(efth).all()
    # 2 times x 1 wet row x 3 lons
    assert out["efth"].attrs["fit_n_points"] == 6


def test_blocking_is_a_memory_knob_only():
    """`point_block` bounds the dense float64 intermediate, nothing else.

    The window is uniform on purpose: with a family that has a tail axis the
    tail exponent is chosen per block by modal vote, so on a heterogeneous
    window the block size is not strictly neutral. It is neutral here, and
    with the default Elfouhaily wind sea -- which has an intrinsic tail and
    no tail stage at all -- it is neutral everywhere.
    """
    window = make_window(n_time=3, n_lat=4, n_lon=5)
    whole = spectra_from_partitions(window, point_block=DEFAULT_POINT_BLOCK)
    blocked = spectra_from_partitions(window, point_block=7)
    np.testing.assert_array_equal(whole["efth"].values, blocked["efth"].values)


def test_fit_diagnostics_are_summarised_into_scalars():
    """The one-variable contract means per-point diagnostics cannot be fields."""
    out = spectra_from_partitions(make_window())
    assert list(out.data_vars) == ["efth"]
    for key in (
        "fit_n_points",
        "fit_residual_median",
        "mean_n_partitions",
        "energy_closure_median",
        "fraction_underconstrained_windsea",
    ):
        assert np.isscalar(out["efth"].attrs[key])


def test_tail_fit_is_reported_as_off_without_t02():
    out = spectra_from_partitions(make_window(drop=(T02_FIELD,)))
    assert out["efth"].attrs["tail_exponent_fitted"].startswith("no")


# --------------------------------------------------------------------------
# spectral grid validation
# --------------------------------------------------------------------------


def test_non_geometric_frequency_axis_is_rejected():
    """ww3recon takes df from the first two entries, so this must not pass."""
    with pytest.raises(ValueError, match="geometric ladder"):
        spectra_from_partitions(make_window(), frequency=np.linspace(0.04, 0.5, 20))


def test_non_uniform_direction_axis_is_rejected():
    with pytest.raises(ValueError, match="uniformly spaced"):
        spectra_from_partitions(
            make_window(), direction=np.array([0.0, 10.0, 45.0, 90.0, 200.0])
        )


def test_native_grid_matches_the_archive():
    grid = iowaga_spectral_grid()
    assert grid.n_freq == 36 and grid.n_dir == DEFAULT_N_DIRECTIONS
    np.testing.assert_allclose(grid.f, iowaga_frequencies())
    # WW3's own bin width for a geometric ladder, not a trapezoid.
    ratio = grid.f[1] / grid.f[0]
    np.testing.assert_allclose(grid.df, grid.f * (ratio - 1.0 / ratio) / 2.0)


# --------------------------------------------------------------------------
# window selection
# --------------------------------------------------------------------------


def test_select_window_handles_descending_latitude():
    window = make_window(n_lat=8, lat_ascending=False)
    selected = _select_window(
        window,
        ["2020-01-01T00", "2020-01-01T06"],
        lat_min=48.0,
        lat_max=49.0,
        lon_min=-32.0,
        lon_max=-31.5,
        buffer_deg=0.0,
    )
    assert selected.sizes["latitude"] > 0


def test_select_window_crossing_the_antimeridian():
    window = make_window(n_lon=12, lon_start=175.0)
    lons = window["longitude"].values.copy()
    lons[lons >= 180.0] -= 360.0
    window = window.assign_coords(longitude=lons).sortby("longitude")
    selected = _select_window(
        window,
        ["2020-01-01T00", "2020-01-01T06"],
        lat_min=47.0,
        lat_max=48.0,
        lon_min=178.0,
        lon_max=-178.0,
        buffer_deg=0.0,
    )
    picked = selected["longitude"].values
    assert (picked >= 178.0).any() and (picked <= -178.0).any()


def test_select_window_rejects_an_empty_spatial_selection():
    with pytest.raises(ValueError, match="No IOWAGA grid points"):
        _select_window(
            make_window(),
            ["2020-01-01T00", "2020-01-01T06"],
            lat_min=-60.0,
            lat_max=-59.0,
            lon_min=-33.0,
            lon_max=-32.0,
            buffer_deg=0.0,
        )


# --------------------------------------------------------------------------
# months, urls, coverage
# --------------------------------------------------------------------------


def test_months_in_range_is_inclusive_at_both_ends():
    assert months_in_range(["2020-01-15", "2020-03-02"]) == [
        (2020, 1),
        (2020, 2),
        (2020, 3),
    ]
    assert months_in_range(["2020-05-01", "2020-05-31"]) == [(2020, 5)]


def test_months_in_range_rejects_backwards_dates():
    with pytest.raises(ValueError, match="backwards"):
        months_in_range(["2020-05-01", "2020-04-01"])


def test_build_month_url_matches_the_published_layout():
    url = build_month_url(2020, 7)
    assert url.endswith("GLOB-30M/2020/FIELD_NC/LOPS_WW3-GLOB-30M_202007.nc")
    assert url.startswith("https://data-dataref.ifremer.fr/")


def test_partition_variable_names_covers_every_partition_plus_the_moments():
    names = partition_variable_names()
    assert len(names) == 5 * N_PARTITIONS + 3
    for index in range(N_PARTITIONS):
        for field in ("phs", "ptp", "pdir", "pspr", "pws"):
            assert f"{field}{index}" in names
    # The shape fit needs the whole-spectrum moments, so they have to be part
    # of what gets downloaded -- not just the partitions.
    assert {"hs", T0M1_FIELD, T02_FIELD} <= set(names)


def test_coverage_rejects_dates_before_the_hindcast_starts():
    """Checked before any network call, so no monkeypatch needed."""
    with pytest.raises(ValueError, match="begins 1993"):
        check_coverage(["1992-06-01", "1992-06-05"])


def test_coverage_rejects_an_unpublished_month(monkeypatch):
    monkeypatch.setattr(iowaga, "available_months", lambda year, **kw: [1, 2, 3])
    with pytest.raises(ValueError, match="no GLOB-30M data for 2026-04"):
        check_coverage(["2026-04-01", "2026-04-05"])


def test_coverage_accepts_a_published_month(monkeypatch):
    monkeypatch.setattr(
        iowaga, "available_months", lambda year, **kw: list(range(1, 13))
    )
    check_coverage(["2020-01-01", "2020-02-15"])


def test_coverage_error_names_what_is_published(monkeypatch):
    monkeypatch.setattr(iowaga, "available_months", lambda year, **kw: [1, 2])
    with pytest.raises(ValueError, match="Published for that year: 01, 02"):
        check_coverage(["2026-05-01", "2026-05-02"])


# --------------------------------------------------------------------------
# product contract
# --------------------------------------------------------------------------


def test_product_declares_the_forcing_metadata_contract():
    metadata = IOWAGA.write_metadata()
    for field in (
        "product_name",
        "description",
        "link",
        "time_var_name",
        "time_units",
        "cf_calendar",
        "cesm_calendar",
        "mom6_calendar",
    ):
        assert field in metadata
    assert metadata["product_name"] == "iowaga"


def test_variables_argument_is_rejected():
    with pytest.raises(ValueError, match="does not take a `variables` list"):
        IOWAGA.get_iowaga_2d_spectra(
            dates=["2020-01-01", "2020-01-02"],
            lat_min=47.0,
            lat_max=48.0,
            lon_min=-33.0,
            lon_max=-32.0,
            variables=["hs"],
        )


def test_validate_method_reports_not_auto_validatable():
    """The nightly registry sweep must not download 2.8 GB from Ifremer."""
    assert IOWAGA.validate_method("get_iowaga_2d_spectra") is False


@pytest.mark.slow
def test_live_download_and_reconstruction(tmp_path):
    """Real ~2.8 GB download from data-dataref.ifremer.fr. Run with --runslow."""
    path = IOWAGA.get_iowaga_2d_spectra(
        dates=["2020-01-01 00:00:00", "2020-01-01 12:00:00"],
        lat_min=49.0,
        lat_max=51.0,
        lon_min=-31.0,
        lon_max=-29.0,
        output_folder=tmp_path,
        output_filename="iowaga_live.nc",
    )
    with xr.open_dataset(path) as ds:
        assert list(ds.data_vars) == ["efth"]
        assert ds["efth"].attrs["hs_check"] == "passed"
        assert np.isfinite(ds["efth"].values).all()
        assert float(ds["efth"].max()) > 0.0
        assert ds["efth"].attrs["shape_parameters_fitted"].startswith("yes")
        assert ds["efth"].attrs["fit_n_points"] > 0
