"""Tests for the IOWAGA OPeNDAP wave-spectra product.

Everything here except the one `slow`-marked test is offline: the assembly
step (`spectra_from_iowaga`) and the window selection are pure, so they are
exercised against a fabricated IOWAGA-shaped dataset with no network. That
mirrors how the ERA5 products are split, and it means the parts most likely
to break silently -- the log10 decoding and the directional normalization --
are covered by fast tests.
"""

import numpy as np
import pytest
import xarray as xr

from CrocoDash.raw_data_access.datasets.iowaga import (
    DEFAULT_DATASET,
    EF_LOG_OFFSET,
    IOWAGA,
    build_opendap_url,
    check_coverage,
    cosine_2s_spread,
    decode_ef_spectrum,
    significant_height_from_ef,
    spectra_from_iowaga,
    verify_hs_against_source,
    _load_window,
    _select_window,
    _time_index_slice,
)

# --------------------------------------------------------------------------
# Fabricated IOWAGA window
# --------------------------------------------------------------------------


def make_window(
    n_time=3,
    n_lat=4,
    n_lon=5,
    n_freq=32,
    hs=2.0,
    spread_deg=25.0,
    mean_dir_deg=210.0,
    lon_start=-33.0,
    lat_ascending=True,
):
    """An IOWAGA-shaped window whose spectrum has a known significant height.

    `ef` is stored the way the real dataset stores it -- as a base-10
    logarithm -- so a test that skips `decode_ef_spectrum` gets a wrong
    answer, which is the point.

    The 1D spectrum is a narrow Gaussian in frequency scaled so that
    4*sqrt(integral E df) == `hs` under the same trapezoid the module uses,
    making Hs conservation checkable to floating-point rather than to a
    quadrature tolerance.
    """
    frequency = 0.0373 * 1.1 ** np.arange(n_freq)
    shape = np.exp(-(((frequency - 0.12) / 0.03) ** 2))
    m0_shape = np.trapezoid(shape, x=frequency)
    scale = (hs / 4.0) ** 2 / m0_shape
    ef_linear = np.broadcast_to(
        (shape * scale)[None, None, None, :], (n_time, n_lat, n_lon, n_freq)
    ).copy()

    lat = np.linspace(47.0, 47.0 + 0.5 * (n_lat - 1), n_lat)
    if not lat_ascending:
        lat = lat[::-1]

    return xr.Dataset(
        {
            "ef": (
                ("time", "latitude", "longitude", "f"),
                np.log10(ef_linear + EF_LOG_OFFSET),
            ),
            "dir": (
                ("time", "latitude", "longitude"),
                np.full((n_time, n_lat, n_lon), mean_dir_deg),
            ),
            "spr": (
                ("time", "latitude", "longitude"),
                np.full((n_time, n_lat, n_lon), spread_deg),
            ),
            "hs": (
                ("time", "latitude", "longitude"),
                np.full((n_time, n_lat, n_lon), hs),
            ),
        },
        coords={
            "time": np.array(
                ["2015-01-01T00", "2015-01-01T03", "2015-01-01T06"],
                dtype="datetime64[ns]",
            )[:n_time],
            "latitude": lat,
            "longitude": lon_start + 0.5 * np.arange(n_lon),
            "f": frequency,
        },
    )


def hs_from_efth(ds):
    """Recompute Hs from a written 2D spectrum, integrating over f AND theta."""
    dtheta = np.deg2rad(360.0 / ds.sizes["direction"])
    m0 = np.trapezoid(
        ds["efth"].sum("direction").values * dtheta, x=ds["frequency"].values, axis=-1
    )
    return 4.0 * np.sqrt(np.clip(m0, 0.0, None))


# --------------------------------------------------------------------------
# log10 decoding
# --------------------------------------------------------------------------


def test_decode_ef_spectrum_round_trips():
    linear = np.array([0.0, 1e-8, 0.5, 12.0])
    assert np.allclose(decode_ef_spectrum(np.log10(linear + EF_LOG_OFFSET)), linear)


def test_decode_ef_spectrum_clips_negatives():
    """Values at the encoding floor must not come back negative -- a negative
    spectral density would make the Hs integral imaginary."""
    assert (decode_ef_spectrum(np.array([-30.0, -14.0])) >= 0.0).all()


def test_significant_height_from_ef_matches_construction():
    window = make_window(hs=3.5)
    linear = decode_ef_spectrum(window["ef"].values)
    hs = significant_height_from_ef(linear, window["f"].values)
    assert np.allclose(hs, 3.5, rtol=1e-6)


# --------------------------------------------------------------------------
# directional distribution
# --------------------------------------------------------------------------


@pytest.mark.parametrize("spread", [1.0, 5.0, 15.0, 30.0, 60.0, 90.0, 0.0, np.nan])
def test_cosine_2s_spread_integrates_to_one(spread):
    """Normalization is what makes Hs conservative, so it must hold for every
    spread including the degenerate ones (zero, NaN, and beyond the sqrt(2)
    rad isotropic limit of this family)."""
    direction = np.arange(24) * 15.0
    lobe = cosine_2s_spread(direction, np.array([45.0]), np.array([spread]))
    integral = lobe.sum(axis=-1) * (2 * np.pi / 24)
    assert np.allclose(integral, 1.0)


def test_cosine_2s_spread_peaks_at_mean_direction():
    direction = np.arange(24) * 15.0
    lobe = cosine_2s_spread(direction, np.array([135.0]), np.array([20.0]))
    assert direction[int(np.argmax(lobe))] == 135.0


def test_cosine_2s_spread_narrow_lobe_does_not_underflow():
    """Regression test for the reason this is computed in log space.

    A 1-degree spread puts s in the thousands, and evaluating
    cos(x)**(2s) directly underflows to zero in *every* bin -- including the
    peak -- silently yielding an all-zero spectrum rather than a narrow one.
    """
    direction = np.arange(24) * 15.0
    lobe = cosine_2s_spread(direction, np.array([90.0]), np.array([1.0]))
    assert lobe.max() > 0.0
    assert np.isfinite(lobe).all()
    # All the energy collapses into the single bin at the mean direction.
    assert np.isclose(lobe.max(), 1.0 / (2 * np.pi / 24))


def test_lobe_is_centred_on_dir_unrotated():
    """Pins the direction convention.

    `dir` is `sea_surface_wave_from_direction` and
    forcing/ww3.py::write_ww3_boundary_spectrum documents its `direction`
    argument as the same "coming from" convention, so the lobe must sit ON
    `dir`, not 180 degrees away. Verified against IOWAGA's own point spectra
    (see the module docstring); note those declare a *to*-direction axis, so
    a naive comparison against them looks exactly backwards.
    """
    out = spectra_from_iowaga(make_window(mean_dir_deg=210.0), n_directions=24)
    energy = out["efth"].isel(time=0, latitude=0, longitude=0).sum("frequency")
    peak = float(out["direction"].values[int(np.argmax(energy.values))])
    assert peak == 210.0, f"lobe peaked at {peak}, expected 210 (coming-from)"


def test_output_direction_axis_documents_the_convention():
    out = spectra_from_iowaga(make_window())
    comment = out["direction"].attrs.get("comment", "")
    assert "coming FROM" in comment


def test_cosine_2s_spread_nan_direction_is_uniform_not_nan():
    """Land points carry NaN direction; they must not poison the output."""
    direction = np.arange(24) * 15.0
    lobe = cosine_2s_spread(direction, np.array([np.nan]), np.array([20.0]))
    assert np.isfinite(lobe).all()
    assert np.allclose(lobe, lobe[..., 0])


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------


def test_spectra_from_iowaga_has_exactly_one_variable():
    """forcing/ww3.py::_extract_all_stations does `(var_name,) = ds.data_vars`,
    so a second variable breaks the WW3 pipeline with an unpacking error."""
    out = spectra_from_iowaga(make_window())
    assert list(out.data_vars) == ["efth"]


def test_spectra_from_iowaga_dims_match_the_ww3_contract():
    out = spectra_from_iowaga(make_window(), n_directions=24)
    assert out["efth"].dims == (
        "time",
        "latitude",
        "longitude",
        "frequency",
        "direction",
    )
    assert out.sizes["direction"] == 24
    assert out.sizes["frequency"] == 32


def test_spectra_from_iowaga_conserves_significant_height():
    """End-to-end: the written 2D spectrum integrates back to the Hs the
    source dataset published."""
    out = spectra_from_iowaga(make_window(hs=4.25))
    assert np.allclose(hs_from_efth(out), 4.25, rtol=2e-3)


@pytest.mark.parametrize("n_directions", [12, 24, 36])
def test_hs_conservation_is_independent_of_direction_count(n_directions):
    """Numerical rather than analytic normalization means the directional
    resolution must not change the total energy."""
    out = spectra_from_iowaga(make_window(hs=2.0), n_directions=n_directions)
    assert np.allclose(hs_from_efth(out), 2.0, rtol=2e-3)


def test_spectra_from_iowaga_rejects_missing_variables():
    window = make_window().drop_vars("spr")
    with pytest.raises(KeyError, match="spr"):
        spectra_from_iowaga(window)


def test_hs_self_check_catches_a_wrong_decoding():
    """The self-check exists to catch exactly this: treating `ef` as if it
    were already linear instead of a base-10 logarithm."""
    window = make_window(hs=3.0)
    undecoded = window["ef"].values  # skipping the 10** step
    with pytest.raises(ValueError, match="self-check"):
        verify_hs_against_source(undecoded, window["f"].values, window["hs"].values)


def test_hs_self_check_records_diagnostics_in_attrs():
    out = spectra_from_iowaga(make_window(hs=2.5))
    assert out["efth"].attrs["hs_check"] == "passed"
    assert out["efth"].attrs["hs_check_n_points"] > 0
    assert out["efth"].attrs["ef_decoding"] == "E(f) = 10**ef - 1e-12"


def test_spectra_from_iowaga_skips_the_check_without_hs():
    out = spectra_from_iowaga(make_window().drop_vars("hs"))
    assert "skipped" in out["efth"].attrs["hs_check"]


# --------------------------------------------------------------------------
# window selection
# --------------------------------------------------------------------------


def test_select_window_handles_descending_latitude():
    """xarray's .sel with a slice silently returns nothing when the slice runs
    opposite to the coordinate's order."""
    window = make_window(n_lat=8, lat_ascending=False)
    pieces = _select_window(
        window,
        ["2015-01-01T00", "2015-01-01T06"],
        lat_min=48.0,
        lat_max=49.0,
        lon_min=-32.0,
        lon_max=-31.5,
        buffer_deg=0.0,
    )
    assert _load_window(pieces).sizes["latitude"] > 0


def test_select_window_returns_one_piece_away_from_the_seam():
    pieces = _select_window(
        make_window(),
        ["2015-01-01T00", "2015-01-01T06"],
        lat_min=47.0,
        lat_max=48.0,
        lon_min=-33.0,
        lon_max=-32.0,
        buffer_deg=0.0,
    )
    assert len(pieces) == 1


def test_select_window_crossing_the_antimeridian_concatenates():
    window = make_window(n_lon=12, lon_start=175.0)
    # Longitudes 175.0 .. 180.5 -- rewrite the tail onto the negative branch
    # so the axis looks like the real -180..179.5 one.
    lons = window["longitude"].values.copy()
    lons[lons >= 180.0] -= 360.0
    window = window.assign_coords(longitude=lons).sortby("longitude")
    pieces = _select_window(
        window,
        ["2015-01-01T00", "2015-01-01T06"],
        lat_min=47.0,
        lat_max=48.0,
        lon_min=178.0,
        lon_max=-178.0,
        buffer_deg=0.0,
    )
    # Two contiguous requests, not one selection across the seam.
    assert len(pieces) == 2
    picked = _load_window(pieces)["longitude"].values
    assert (picked >= 178.0).any() and (picked <= -178.0).any()


def test_select_window_rejects_an_empty_spatial_selection():
    with pytest.raises(ValueError, match="No IOWAGA grid points"):
        _select_window(
            make_window(),
            ["2015-01-01T00", "2015-01-01T06"],
            lat_min=-60.0,
            lat_max=-59.0,
            lon_min=-33.0,
            lon_max=-32.0,
            buffer_deg=0.0,
        )


def test_time_index_slice_is_contiguous_and_covers_the_range():
    """An integer slice keeps the fetch to one contiguous OPeNDAP request."""
    window = make_window()
    sel = _time_index_slice(window["time"].values, ["2015-01-01T00", "2015-01-01T03"])
    assert isinstance(sel, slice)
    assert window["time"].values[sel].size == 2


def test_time_index_slice_rejects_a_non_monotonic_span():
    """The real aggregation repeats each 2018-2019 month out of order; a slice
    of that cannot be trusted, so it must raise rather than return garbage."""
    window = make_window()
    scrambled = window["time"].values.copy()
    scrambled[1], scrambled[2] = scrambled[2], scrambled[1]
    with pytest.raises(ValueError, match="not monotonic"):
        _time_index_slice(scrambled, ["2015-01-01T00", "2015-01-01T06"])


def test_select_window_rejects_an_empty_time_selection():
    with pytest.raises(ValueError, match="No IOWAGA time steps"):
        _select_window(
            make_window(),
            ["2016-01-01T00", "2016-01-02T00"],
            lat_min=47.0,
            lat_max=48.0,
            lon_min=-33.0,
            lon_max=-32.0,
            buffer_deg=0.0,
        )


# --------------------------------------------------------------------------
# product contract
# --------------------------------------------------------------------------


def test_coverage_guard_rejects_dates_outside_the_record():
    """The OPeNDAP service carries the 1991-2019 ECMWF-forced hindcast, not
    the newer ERA5-forced one -- an out-of-range .sel would silently return a
    short record rather than erroring."""
    with pytest.raises(ValueError, match="broken from 2018|usable from"):
        check_coverage(["2021-01-01", "2021-01-02"])
    with pytest.raises(ValueError):
        check_coverage(["1990-01-01", "1990-01-02"])


def test_coverage_guard_accepts_dates_inside_the_record():
    check_coverage(["2015-01-01", "2015-02-01"])


def test_coverage_guard_rejects_the_corrupt_2018_onward_region():
    """The aggregation advertises data to 2019-12-31, but its time axis is
    duplicated and out of order from 2018 on."""
    with pytest.raises(ValueError, match="broken from 2018"):
        check_coverage(["2018-06-01", "2018-06-05"])
    with pytest.raises(ValueError):
        check_coverage(["2019-01-01", "2019-01-02"])


def test_coverage_guard_is_not_claimed_for_other_aggregations():
    check_coverage(["2021-01-01", "2021-01-02"], dataset="IOWAGA-SOMETHING-ELSE")


def test_opendap_url_is_built_from_the_dataset_name():
    assert build_opendap_url(DEFAULT_DATASET).endswith(DEFAULT_DATASET)
    assert build_opendap_url(DEFAULT_DATASET).startswith("https://")


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
    """`variables` exists only to satisfy ForcingProduct.required_args; the
    fetch is fixed at ef/dir/spr/hs, so a caller passing one is confused."""
    with pytest.raises(ValueError, match="does not take a `variables` list"):
        IOWAGA.get_iowaga_2d_spectra(
            dates=["2015-01-01", "2015-01-02"],
            lat_min=47.0,
            lat_max=48.0,
            lon_min=-33.0,
            lon_max=-32.0,
            variables=["hs"],
        )


def test_validate_method_reports_not_auto_validatable():
    """The nightly registry sweep must not make a live third-party request."""
    assert IOWAGA.validate_method("get_iowaga_2d_spectra") is False


@pytest.mark.slow
def test_live_opendap_pull(tmp_path):
    """Real request to tds3.ifremer.fr. Run with --runslow."""
    path = IOWAGA.get_iowaga_2d_spectra(
        dates=["2015-01-01 00:00:00", "2015-01-01 12:00:00"],
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
