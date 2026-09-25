"""Tests for WW3Configurator and its process()-adjacent helpers."""

import os
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from CrocoDash.forcing import ww3
from CrocoDash.forcing.base import WorkflowContext
from CrocoDash.forcing.ww3 import WAVE_SUBDIR, WW3Configurator
from CrocoDash.raw_data_access.base import (
    DIRECTION_COMING_FROM,
    DIRECTION_TO,
    GREGORIAN,
    LAND_NAN,
    LAND_ZERO,
    WW3ForcingProduct,
    accessmethod,
)


def _make_ctx(tmp_path, **overrides):
    defaults = dict(
        inputdir=tmp_path,
        supergrid_path=tmp_path / "grid.nc",
        vgrid_path=tmp_path / "vgrid.nc",
        topo_path=tmp_path / "topo.nc",
        raw_data_dir=tmp_path,
        regridded_data_dir=tmp_path,
        output_path=tmp_path,
        config={
            "conditions": {
                "inputs": {"start_date": "2020-01-01", "end_date": "2020-01-02"}
            }
        },
    )
    defaults.update(overrides)
    return WorkflowContext(**defaults)


# =============================================================================
# write_ww3_boundary_spectrum / write_ww3_bounc_nml / write_spec_list
# =============================================================================


def test_write_ww3_boundary_spectrum_default_time(tmp_path):
    freq = 0.04118 * 1.1 ** np.arange(5)
    direction = np.linspace(0, 360, 4, endpoint=False)
    efth = np.ones((1, 5, 4))
    path = tmp_path / "point_spec.nc"

    ww3.write_ww3_boundary_spectrum(
        path, lat=10.0, lon=200.0, freq=freq, direction=direction, efth=efth
    )

    ds = xr.open_dataset(path, decode_times=False, mask_and_scale=False)
    try:
        assert ds["efth"].shape == (1, 5, 4, 1, 1)
        assert ds["efth"].attrs["_FillValue"] == pytest.approx(-999.9, rel=1e-4)
        assert ds["efth"].attrs["scale_factor"] == pytest.approx(1.0)
        assert ds["efth"].attrs["add_offset"] == pytest.approx(0.0)
        assert ds["time"].attrs["units"] == "seconds since 1990-01-01 00:00:00.0"
        assert ds["time"].attrs["calendar"] == "gregorian"
        assert float(ds["latitude"].values[0]) == pytest.approx(10.0)
        assert float(ds["longitude"].values[0]) == pytest.approx(200.0)
        # No spurious _FillValue on any coordinate (xarray adds these by
        # default unless explicitly suppressed -- see write_ww3_boundary_spectrum)
        for coord in ("time", "frequency", "direction", "latitude", "longitude"):
            assert "_FillValue" not in ds[coord].attrs
    finally:
        ds.close()


def test_write_ww3_boundary_spectrum_time_units_untouched_by_xarray(tmp_path):
    """
    Regression test for the xarray CF-encoder bug found this session: writing
    a midnight-exact datetime64 time coordinate directly (instead of plain
    float seconds) causes xarray to silently rewrite the "units" attribute,
    dropping the "hh:mm:ss" portion -- which corrupts W3TIMEMD's fixed
    column-position parser in ww3_bounc.
    """
    freq = 0.04118 * 1.1 ** np.arange(3)
    direction = np.linspace(0, 360, 4, endpoint=False)
    time = np.array(["2020-01-01T00:00:00"], dtype="datetime64[ns]")
    efth = np.ones((1, 3, 4))
    path = tmp_path / "point_spec.nc"

    ww3.write_ww3_boundary_spectrum(
        path, lat=0.0, lon=0.0, freq=freq, direction=direction, efth=efth, time=time
    )

    ds = xr.open_dataset(path, decode_times=False, mask_and_scale=False)
    try:
        assert ds["time"].attrs["units"] == "seconds since 1990-01-01 00:00:00.0"
        expected_seconds = (
            time[0] - np.datetime64("1990-01-01T00:00:00", "ns")
        ) / np.timedelta64(1, "s")
        assert float(ds["time"].values[0]) == pytest.approx(expected_seconds)
    finally:
        ds.close()


def test_write_ww3_bounc_nml(tmp_path):
    ww3.write_ww3_bounc_nml(
        tmp_path, spec_list_filename="foo.list", mode="READ", interp=1, verbose=2
    )

    content = (tmp_path / "ww3_bounc.nml").read_text()
    assert "BOUND%MODE                 = 'READ'" in content
    assert "BOUND%INTERP               = 1" in content
    assert "BOUND%VERBOSE              = 2" in content
    assert "BOUND%FILE                 = 'foo.list'" in content


def test_write_spec_list(tmp_path):
    ww3.write_spec_list(tmp_path, ["a_spec.nc", "b_spec.nc"])

    content = (tmp_path / "spec.list").read_text()
    assert content == "a_spec.nc\nb_spec.nc\n"


# =============================================================================
# WW3Configurator.process()
# =============================================================================


def test_process_ww3_obc_skipped_with_none_product(tmp_path, gen_grid_topo_vgrid):
    """ww3_obc_product_name='none' is the explicit opt-out: process() must
    generate nothing at all rather than fall back to a default product."""
    grid, topo, vgrid = gen_grid_topo_vgrid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)

    configurator = WW3Configurator(
        case_inputdir=tmp_path, boundaries=["west"], ww3_obc_product_name="none"
    )

    with patch("CrocoDash.forcing.ww3.obc.process_obc_conditions") as mock_process:
        configurator.process(_make_ctx(tmp_path, supergrid_path=hgrid_path))

    mock_process.assert_not_called()

    # No spec.list / ww3_bounc.nml / point files -- but WW3_GRID_INP_DIR still
    # has to name a directory that exists, since CIME's ww3 buildnml reads it.
    wave_dir = tmp_path / WAVE_SUBDIR
    assert wave_dir.is_dir()
    assert list(wave_dir.iterdir()) == []


@pytest.mark.parametrize(
    "kwargs, given, missing",
    [
        (
            {"ww3_obc_product_name": "era5_wave_spectra"},
            "ww3_obc_product_name",
            "ww3_obc_function_name",
        ),
        (
            {"ww3_obc_function_name": "get_era5_2d_spectra"},
            "ww3_obc_function_name",
            "ww3_obc_product_name",
        ),
    ],
)
def test_process_ww3_obc_half_specified_raises(tmp_path, kwargs, given, missing):
    """Only one of the pair given is a typo or a forgotten argument, not a
    request to skip -- rejected up front rather than hidden behind a case
    that still runs."""
    with pytest.raises(ValueError, match=f"{given} was given but {missing}"):
        WW3Configurator(case_inputdir=tmp_path, boundaries=["west"], **kwargs)


def _make_synthetic_era5_window(n_stations=3):
    """Synthetic dataset matching the real decoded ERA5 shape (see
    raw_data_access.datasets.era5.decode_era5_spectra_grib) -- a regular
    (time, latitude, longitude, frequency, direction) grid -- so the real
    regrid logic can be exercised without any network/GRIB dependency. Uses
    a single latitude row (n_stations longitude columns), so each (lat, lon)
    point maps 1:1 onto a station index k after _extract_all_stations's
    stack, with a distinct, checkable efth value (100 + k) confirming no
    station gets reduced/averaged with another.
    """
    time = pd.date_range("2020-01-01", periods=4, freq="6h")
    freq = np.array([0.05, 0.1, 0.15])
    direction = np.array([0.0, 120.0, 240.0])
    lons = np.linspace(-170.0, -160.0, n_stations)
    lats = np.array([68.5])
    efth = np.zeros((len(time), 1, n_stations, len(freq), len(direction)))
    for k in range(n_stations):
        efth[:, 0, k, :, :] = 100.0 + k
    return xr.Dataset(
        {
            "wave_spectra": (
                ("time", "latitude", "longitude", "frequency", "direction"),
                efth,
            )
        },
        coords={
            "time": time.values,
            "latitude": lats,
            "longitude": lons,
            "frequency": freq,
            "direction": direction,
        },
    )


def test_extract_all_stations_keeps_every_point():
    ds = _make_synthetic_era5_window(n_stations=3)
    lons, lats, freq, direction, efth = ww3._extract_all_stations(ds)

    assert list(lons) == list(ds["longitude"].values)
    assert list(lats) == [68.5, 68.5, 68.5]
    assert list(freq) == list(ds["frequency"].values)
    assert list(direction) == list(ds["direction"].values)
    assert efth.shape == (3, 4, 3, 3)  # (station, time, frequency, direction)
    for k in range(3):
        assert np.all(efth[k] == 100.0 + k)


def test_extract_all_stations_drops_zero_stations_for_a_land_zero_product():
    ds = _make_synthetic_era5_window(n_stations=3)
    ds["wave_spectra"][:, :, 1, :, :] = 0.0  # middle station reads as land
    lons, lats, freq, direction, efth = ww3._extract_all_stations(
        ds, land_marker=LAND_ZERO
    )
    assert len(lons) == 2


def test_extract_all_stations_keeps_zero_stations_for_a_land_nan_product():
    """The sea-ice case: every bin is exactly zero, but the point is water
    and zero is the boundary condition ww3_bounc must be given."""
    ds = _make_synthetic_era5_window(n_stations=3)
    ds["wave_spectra"][:, :, 1, :, :] = 0.0  # iced over, not land
    lons, lats, freq, direction, efth = ww3._extract_all_stations(
        ds, land_marker=LAND_NAN
    )
    assert len(lons) == 3
    assert np.all(efth[1] == 0.0)


def test_extract_all_stations_drops_nan_stations_for_a_land_nan_product():
    ds = _make_synthetic_era5_window(n_stations=3)
    ds["wave_spectra"][:, :, 1, :, :] = np.nan
    lons, lats, freq, direction, efth = ww3._extract_all_stations(
        ds, land_marker=LAND_NAN
    )
    assert len(lons) == 2
    assert np.isfinite(efth).all()


def test_extract_all_stations_raises_only_when_every_station_is_land():
    ds = _make_synthetic_era5_window(n_stations=3)
    ds["wave_spectra"][:] = np.nan
    with pytest.raises(ValueError, match="all-NaN"):
        ww3._extract_all_stations(ds, land_marker=LAND_NAN)


def test_extract_all_stations_rejects_an_unknown_land_marker():
    ds = _make_synthetic_era5_window(n_stations=3)
    with pytest.raises(ValueError, match="Unknown land marker"):
        ww3._extract_all_stations(ds, land_marker="masked")


def test_extract_all_stations_shape_mismatch_raises():
    # Missing the "direction" dim entirely -- should trigger the check.
    bad = xr.Dataset(
        {
            "wave_spectra": (
                ("time", "latitude", "longitude", "frequency"),
                np.ones((4, 1, 3, 3)),
            )
        },
        coords={
            "time": pd.date_range("2020-01-01", periods=4, freq="6h").values,
            "latitude": [68.5],
            "longitude": [1.0, 2.0, 3.0],
            "frequency": [0.05, 0.1, 0.15],
        },
    )
    with pytest.raises(ValueError, match="direction"):
        ww3._extract_all_stations(bad)


def test_wrap_lons_like():
    lons = np.array([190.0, 205.0, 10.0])
    assert np.allclose(
        ww3._wrap_lons_like(lons, np.array([-170.0, -155.0])), [-170, -155, 10]
    )
    assert np.allclose(ww3._wrap_lons_like(lons - 360, np.array([190.0, 205.0])), lons)


def test_to_direction_to_leaves_a_to_product_alone():
    direction = np.array([90.0, 75.0, 0.0, 345.0])
    assert np.all(ww3.to_direction_to(direction, DIRECTION_TO) == direction)


def test_to_direction_to_rotates_a_coming_from_product_by_180():
    direction = np.array([0.0, 90.0, 190.0, 359.0])
    assert ww3.to_direction_to(direction, DIRECTION_COMING_FROM) == pytest.approx(
        [180.0, 270.0, 10.0, 179.0]
    )


def test_to_direction_to_rejects_an_unknown_convention():
    with pytest.raises(ValueError, match="Unknown direction convention"):
        ww3.to_direction_to(np.array([0.0]), "nautical-ish")


def test_regrid_chunk_spectra_converts_a_coming_from_product(tmp_path):
    """The axis moves; efth does not -- it is indexed by that axis."""
    ds = _make_synthetic_era5_window(n_stations=3)

    ww3._regrid_chunk_spectra(
        ds=ds,
        hgrid=None,
        boundary="west",
        seg_id=4,
        outfolder=tmp_path,
        dataset_varnames={
            "direction_convention": DIRECTION_COMING_FROM,
            "land_marker": LAND_ZERO,
        },
        start_date="2020-01-01",
        regridders=None,
    )

    out = xr.open_dataset(tmp_path / "forcing_obc_segment_004.nc")
    try:
        assert out["direction"].values == pytest.approx(
            np.mod(ds["direction"].values + 180.0, 360.0)
        )
        for k in range(3):
            assert np.all(out["efth"].isel(station=k).values == 100.0 + k)
    finally:
        out.close()


def test_regrid_chunk_spectra_writes_all_stations(tmp_path):
    ds = _make_synthetic_era5_window(n_stations=3)

    ww3._regrid_chunk_spectra(
        ds=ds,
        hgrid=None,
        boundary="west",
        seg_id=3,
        outfolder=tmp_path,
        dataset_varnames={
            "direction_convention": DIRECTION_TO,
            "land_marker": LAND_ZERO,
        },
        start_date="2020-01-01",
        regridders=None,
    )

    out = xr.open_dataset(tmp_path / "forcing_obc_segment_003.nc")
    try:
        assert out.sizes["station"] == 3
        for k in range(3):
            assert np.all(out["efth"].isel(station=k).values == 100.0 + k)
        assert list(out["station_lon"].values) == list(ds["longitude"].values)
        assert list(out["station_lat"].values) == [68.5, 68.5, 68.5]
    finally:
        out.close()


class _FakeERA5Spectra(WW3ForcingProduct):
    """Test-only stand-in for era5.ERA5_WAVE_SPECTRA -- writes a synthetic
    dataset already in the real decoded ERA5 shape (see
    _make_synthetic_era5_window), instead of hitting CDS/GRIB, so
    WW3Configurator.process's regrid path can be exercised end-to-end
    without network/credentials. Auto-registers on import via
    BaseProduct.__init_subclass__, same as test_base_registry.py's
    DummyProduct/DummyForcing fixtures."""

    product_name = "test_fake_era5_spectra"
    description = "Fake multi-station ERA5-shaped spectra for testing."
    link = "n/a"
    time_var_name = "time"
    time_units = None
    calendar = GREGORIAN
    direction_convention = DIRECTION_COMING_FROM
    land_marker = LAND_ZERO

    @accessmethod
    def get_fake_spectra(
        dates,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        name=None,
        output_folder=Path(""),
        output_filename="fake_era5.nc",
        variables=None,
    ):
        start, end = pd.to_datetime(dates[0]), pd.to_datetime(dates[1])
        time = pd.date_range(start, end, freq="6h")
        freq = np.array([0.05, 0.1, 0.15])
        direction = np.array([0.0, 120.0, 240.0])
        n_stations = 3
        if (lon_max - lon_min) >= (lat_max - lat_min):
            lons = np.linspace(lon_min, lon_max, n_stations)
            lats = np.array([(lat_min + lat_max) / 2])
        else:
            lons = np.array([(lon_min + lon_max) / 2])
            lats = np.linspace(lat_min, lat_max, n_stations)
        efth = np.zeros((len(time), len(lats), len(lons), len(freq), len(direction)))
        for k in range(n_stations):
            j, i = (k, 0) if len(lats) > 1 else (0, k)
            efth[:, j, i, :, :] = 100.0 + k

        ds = xr.Dataset(
            {
                "wave_spectra": (
                    ("time", "latitude", "longitude", "frequency", "direction"),
                    efth,
                )
            },
            coords={
                "time": time.values,
                "latitude": lats,
                "longitude": lons,
                "frequency": freq,
                "direction": direction,
            },
        )
        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)
        path = output_folder / output_filename
        ds.to_netcdf(path)
        return path


def test_process_ww3_obc_multi_station(tmp_path, gen_grid_topo_vgrid):
    grid, topo, vgrid = gen_grid_topo_vgrid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)

    configurator = WW3Configurator(
        case_inputdir=tmp_path,
        boundaries=["west", "east"],
        ww3_obc_product_name="test_fake_era5_spectra",
        ww3_obc_function_name="get_fake_spectra",
    )
    configurator.process(_make_ctx(tmp_path, supergrid_path=hgrid_path))

    wave = tmp_path / WAVE_SUBDIR
    # 2 boundaries x 3 real stations each = 6 total, not 2.
    spec_lines = (wave / "spec.list").read_text().splitlines()
    assert spec_lines == [f"ww3.point{i}_spec.nc" for i in range(1, 7)]

    nml_contents = (wave / "ww3_bounc.nml").read_text()
    assert "BOUND%INTERP               = 2" in nml_contents

    for i, expected_value in zip(range(1, 7), [100.0, 101.0, 102.0] * 2):
        ds = xr.open_dataset(wave / f"ww3.point{i}_spec.nc", decode_times=False)
        try:
            assert np.all(ds["efth"].values == expected_value)
        finally:
            ds.close()


def test_process_ww3_obc_with_reference_waves(tmp_path, gen_grid_topo_vgrid):
    """Same pipeline as test_process_ww3_obc_multi_station, but against the
    shipped, JONSWAP-shaped 'reference_waves' product instead of the
    test-local flat-value fake."""
    grid, topo, vgrid = gen_grid_topo_vgrid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)

    configurator = WW3Configurator(
        case_inputdir=tmp_path,
        boundaries=["west", "east"],
        ww3_obc_product_name="reference_waves",
        ww3_obc_function_name="get_reference_wave_spectra",
    )
    configurator.process(_make_ctx(tmp_path, supergrid_path=hgrid_path))

    wave = tmp_path / WAVE_SUBDIR
    spec_lines = (wave / "spec.list").read_text().splitlines()
    assert spec_lines == [f"ww3.point{i}_spec.nc" for i in range(1, 7)]

    for i in range(1, 7):
        ds = xr.open_dataset(wave / f"ww3.point{i}_spec.nc", decode_times=False)
        try:
            assert np.isfinite(ds["efth"].values).all()
            # Cosine-2s directional spreading legitimately hits exact zero
            # away from the dominant direction -- just check there's energy
            # somewhere and nothing went negative.
            assert np.all(ds["efth"].values >= 0)
            assert np.any(ds["efth"].values > 0)
        finally:
            ds.close()


def test_process_ww3_obc_none_clears_a_previous_runs_spectra(
    tmp_path, gen_grid_topo_vgrid
):
    """Re-processing with 'none' must leave wav/ without spectra: ww3_bounc
    would otherwise rebuild nest.ww3 from the earlier run's files. Anything
    else in wav/ is not process()'s to delete."""
    grid, topo, vgrid = gen_grid_topo_vgrid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)
    ctx = _make_ctx(tmp_path, supergrid_path=hgrid_path)

    WW3Configurator(
        case_inputdir=tmp_path,
        boundaries=["west"],
        ww3_obc_product_name="reference_waves",
        ww3_obc_function_name="get_reference_wave_spectra",
    ).process(ctx)
    wave = tmp_path / WAVE_SUBDIR
    assert (wave / "spec.list").exists()
    (wave / "ww3_grid.inp").write_text("keep me\n")

    WW3Configurator(
        case_inputdir=tmp_path, boundaries=["west"], ww3_obc_product_name="none"
    ).process(ctx)

    assert sorted(p.name for p in wave.iterdir()) == ["ww3_grid.inp"]


def test_process_ww3_obc_failed_rerun_keeps_the_previous_spectra(
    tmp_path, gen_grid_topo_vgrid
):
    """A re-run that fails (network, a database gap) must not leave the case
    with no boundary spectra, which WW3 would silently run as calm."""
    grid, topo, vgrid = gen_grid_topo_vgrid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)
    ctx = _make_ctx(tmp_path, supergrid_path=hgrid_path)
    configurator = WW3Configurator(
        case_inputdir=tmp_path,
        boundaries=["west"],
        ww3_obc_product_name="reference_waves",
        ww3_obc_function_name="get_reference_wave_spectra",
    )
    configurator.process(ctx)
    wave = tmp_path / WAVE_SUBDIR
    before = sorted(p.name for p in wave.iterdir())

    with patch(
        "CrocoDash.forcing.ww3.obc.process_obc_conditions",
        side_effect=RuntimeError("network down"),
    ):
        with pytest.raises(RuntimeError, match="network down"):
            configurator.process(ctx)

    assert sorted(p.name for p in wave.iterdir()) == before


def test_process_ww3_obc_failure_while_writing_keeps_the_previous_spectra(
    tmp_path, gen_grid_topo_vgrid
):
    """Writing the point files is the last step that can fail; the previous
    set must survive it intact, and a good run leaves no staging behind."""
    grid, topo, vgrid = gen_grid_topo_vgrid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)
    ctx = _make_ctx(tmp_path, supergrid_path=hgrid_path)
    configurator = WW3Configurator(
        case_inputdir=tmp_path,
        boundaries=["west"],
        ww3_obc_product_name="reference_waves",
        ww3_obc_function_name="get_reference_wave_spectra",
    )
    configurator.process(ctx)
    wave = tmp_path / WAVE_SUBDIR
    before = {p.name: p.read_bytes() for p in wave.iterdir()}
    assert not (tmp_path / "extract_forcings" / "ww3" / "boundary_spectra").exists()

    real_write = ww3.write_ww3_boundary_spectrum
    calls = []

    def fail_on_second(*args, **kwargs):
        calls.append(args[0])
        if len(calls) == 2:
            raise OSError("disk full")
        return real_write(*args, **kwargs)

    with patch(
        "CrocoDash.forcing.ww3.write_ww3_boundary_spectrum", side_effect=fail_on_second
    ):
        with pytest.raises(OSError, match="disk full"):
            configurator.process(ctx)

    assert {p.name: p.read_bytes() for p in wave.iterdir()} == before


def _reference_waves(tmp_path, boundaries=("west",)):
    return WW3Configurator(
        case_inputdir=tmp_path,
        boundaries=list(boundaries),
        ww3_obc_product_name="reference_waves",
        ww3_obc_function_name="get_reference_wave_spectra",
    )


def test_process_ww3_obc_failure_writing_spec_list_keeps_the_previous_spectra(
    tmp_path, gen_grid_topo_vgrid
):
    """spec.list is written last: failing there, after every point file, must
    still leave the previous set as it was and nothing staged behind."""
    grid, topo, vgrid = gen_grid_topo_vgrid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)
    ctx = _make_ctx(tmp_path, supergrid_path=hgrid_path)
    _reference_waves(tmp_path).process(ctx)
    wave = tmp_path / WAVE_SUBDIR
    before = {p.name: p.read_bytes() for p in wave.iterdir()}

    with patch("CrocoDash.forcing.ww3.write_spec_list", side_effect=OSError("quota")):
        with pytest.raises(OSError, match="quota"):
            _reference_waves(tmp_path, ("west", "east")).process(ctx)

    assert {p.name: p.read_bytes() for p in wave.iterdir()} == before


def test_staged_files_left_by_an_interrupted_run_are_cleared(
    tmp_path, gen_grid_topo_vgrid
):
    grid, topo, vgrid = gen_grid_topo_vgrid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)
    ctx = _make_ctx(tmp_path, supergrid_path=hgrid_path)
    wave = tmp_path / WAVE_SUBDIR
    wave.mkdir(parents=True)
    for name in ("ww3.point9_spec.nc.new", "spec.list.new", "ww3_bounc.nml.new"):
        (wave / name).write_text("from a killed run")

    _reference_waves(tmp_path).process(ctx)
    assert not list(wave.glob("*.new"))
    nml = (wave / "ww3_bounc.nml").read_text()
    assert "  BOUND%FILE                 = 'spec.list'" in nml
    assert "spec.list.new" not in nml

    (wave / "spec.list.new").write_text("from a killed run")
    WW3Configurator(
        case_inputdir=tmp_path, boundaries=["west"], ww3_obc_product_name="none"
    ).process(ctx)
    assert not list(wave.glob("*"))


def _dir_on_another_filesystem(near):
    """A fresh dir on a different device than ``near``, or None."""
    import tempfile

    for candidate in ("/dev/shm", tempfile.gettempdir()):
        if (
            os.path.isdir(candidate)
            and os.access(candidate, os.W_OK)
            and os.stat(candidate).st_dev != os.stat(near).st_dev
        ):
            return Path(tempfile.mkdtemp(dir=candidate))
    return None


def test_process_ww3_obc_extract_forcings_on_another_filesystem(
    tmp_path, gen_grid_topo_vgrid
):
    """A user may symlink extract_forcings/ to scratch; re-running must still
    replace the spectra in wav/, not fail after deleting them."""
    import shutil

    elsewhere = _dir_on_another_filesystem(tmp_path)
    if elsewhere is None:
        pytest.skip("no writable directory on a second filesystem")
    try:
        (tmp_path / "extract_forcings").symlink_to(elsewhere)
        grid, topo, vgrid = gen_grid_topo_vgrid
        hgrid_path = tmp_path / "hgrid.nc"
        grid.write_supergrid(hgrid_path)
        ctx = _make_ctx(tmp_path, supergrid_path=hgrid_path)
        configurator = WW3Configurator(
            case_inputdir=tmp_path,
            boundaries=["west"],
            ww3_obc_product_name="reference_waves",
            ww3_obc_function_name="get_reference_wave_spectra",
        )
        configurator.process(ctx)
        configurator.process(ctx)
        wave = tmp_path / WAVE_SUBDIR
        listed = (wave / "spec.list").read_text().split()
        assert listed and all((wave / name).is_file() for name in listed)
    finally:
        shutil.rmtree(elsewhere)


def test_process_ww3_obc_rerun_with_fewer_stations_drops_the_extra_points(
    tmp_path, gen_grid_topo_vgrid
):
    grid, topo, vgrid = gen_grid_topo_vgrid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)
    ctx = _make_ctx(tmp_path, supergrid_path=hgrid_path)
    wave = tmp_path / WAVE_SUBDIR
    points = lambda: sorted(p.name for p in wave.glob("ww3.point*_spec.nc"))
    for boundaries in (["west", "east"], ["west"]):
        WW3Configurator(
            case_inputdir=tmp_path,
            boundaries=boundaries,
            ww3_obc_product_name="reference_waves",
            ww3_obc_function_name="get_reference_wave_spectra",
        ).process(ctx)
        listed = sorted((wave / "spec.list").read_text().split())
        assert points() == listed

    assert len(listed) == 3  # west only, after 6 for west + east


def test_process_ww3_obc_with_cesm_ww3_jra(
    skip_if_not_glade, tmp_path, gen_grid_topo_vgrid
):
    """The whole GET -> REGRID -> MERGE -> spec.list path against the real
    global WW3 database on GLADE.

    The unit tests in tests/raw_data_access/test_cesm_ww3_jra.py pin the
    conventions against a fabricated restart; this one checks that a real
    600-variable restart, a real coastal window and a real ww3_bounc input
    set actually come out the other end. Skipped off GLADE.
    """
    grid, topo, vgrid = gen_grid_topo_vgrid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)

    configurator = WW3Configurator(
        case_inputdir=tmp_path,
        boundaries=["west", "east"],
        ww3_obc_product_name="CESM-WW3-JRA",
        ww3_obc_function_name="get_cesm_ww3_jra_spectra",
    )
    ctx = _make_ctx(
        tmp_path,
        supergrid_path=hgrid_path,
        config={
            "conditions": {
                "inputs": {"start_date": "2019-06-05", "end_date": "2019-06-05"}
            }
        },
    )
    configurator.process(ctx)

    wave = tmp_path / WAVE_SUBDIR
    spectra = sorted(wave.glob("ww3.point*_spec.nc"))
    assert spectra, "no boundary spectra were written"
    assert (wave / "ww3_bounc.nml").exists()
    assert len((wave / "spec.list").read_text().splitlines()) == len(spectra)

    for path in spectra:
        ds = xr.open_dataset(path, decode_times=False)
        try:
            # ww3_bounc reads these by name; the grid's own discretization.
            assert ds.sizes["frequency"] == 25
            assert ds.sizes["direction"] == 24
            assert ds.sizes["time"] == 4  # 6-hourly over one whole day
            assert np.isfinite(ds["efth"].values).all()
            assert np.all(ds["efth"].values >= 0)
            assert np.any(ds["efth"].values > 0)
            # "to" convention, WW3 index order, passed through unrotated.
            assert float(ds["direction"][0]) == pytest.approx(90.0)
            assert float(ds["direction"][6]) == pytest.approx(0.0)
        finally:
            ds.close()


# =============================================================================
# validate_args / smoke
# =============================================================================


def test_ww3_configurator_requires_product():
    # Leaving ww3_obc_product_name unset is an error; 'none' is the opt-out.
    with pytest.raises(ValueError, match="ww3_obc_product_name is required"):
        WW3Configurator(case_inputdir="dummy", boundaries=["west"])
    WW3Configurator(
        case_inputdir="dummy", boundaries=["west"], ww3_obc_product_name="none"
    )


def test_ww3_configurator_rejects_non_ww3_product():
    # A registered product of the wrong flavor (a MOM6 forcing product) and an
    # entirely unknown name are both rejected, with distinct messages.
    with pytest.raises(ValueError, match="not a WW3ForcingProduct"):
        WW3Configurator(
            case_inputdir="dummy",
            boundaries=["west"],
            ww3_obc_product_name="reference_ocean",
        )

    with pytest.raises(ValueError, match="Unknown forcing product"):
        WW3Configurator(
            case_inputdir="dummy",
            boundaries=["west"],
            ww3_obc_product_name="not_a_real_product",
        )


def test_ww3_configurator_accepts_matching_product():
    # Doesn't raise -- both the real ERA5 spectra product and the fast
    # synthetic stand-in are valid WW3ForcingProducts.
    WW3Configurator(
        case_inputdir="dummy",
        boundaries=["west"],
        ww3_obc_product_name="era5_wave_spectra",
        ww3_obc_function_name="get_era5_2d_spectra",
    )
    WW3Configurator(
        case_inputdir="dummy",
        boundaries=["west"],
        ww3_obc_product_name="reference_waves",
        ww3_obc_function_name="get_reference_wave_spectra",
    )


# =============================================================================
# WW3Configurator.get_output_filepaths()
# =============================================================================
#
# WW3's output_params are all XML settings -- WW3_GRID_INP_DIR even holds a
# directory rather than a file -- so the base implementation, which walks
# output_params for is_file entries, finds nothing. Left that way,
# CaseBundle.bundle() ships a bundle with no WW3 input in it and
# validate_output_filepaths() passes without checking anything.


def _populate_wave_dir(inputdir, n_stations=2):
    """Build a wave/ directory the way process() does, using the real writers."""
    wave_dir = Path(inputdir) / WAVE_SUBDIR
    wave_dir.mkdir(parents=True, exist_ok=True)
    spectra = []
    for k in range(n_stations):
        path = wave_dir / f"ww3.point{k + 1}_spec.nc"
        path.touch()
        spectra.append(str(path))
    ww3.write_spec_list(wave_dir, spectra)
    ww3.write_ww3_bounc_nml(wave_dir, interp=2)
    return wave_dir


def test_get_output_filepaths_empty_when_not_yet_processed(tmp_path):
    (tmp_path / "ocnice").mkdir()
    configurator = WW3Configurator(
        case_inputdir=tmp_path, boundaries=["west"], ww3_obc_product_name="none"
    )
    assert configurator.get_output_filepaths(tmp_path / "ocnice") == []


def test_get_output_filepaths_returns_every_generated_file(tmp_path):
    """Spectra count is not known up front, so this globs rather than names."""
    _populate_wave_dir(tmp_path, n_stations=3)
    configurator = WW3Configurator(
        case_inputdir=tmp_path, boundaries=["west"], ww3_obc_product_name="none"
    )

    names = {
        Path(p).name for p in configurator.get_output_filepaths(tmp_path / "ocnice")
    }
    assert names == {
        "ww3.point1_spec.nc",
        "ww3.point2_spec.nc",
        "ww3.point3_spec.nc",
        "spec.list",
        "ww3_bounc.nml",
    }
    assert configurator.validate_output_filepaths(tmp_path / "ocnice")


def test_get_output_filepaths_skips_subdirectories(tmp_path):
    wave_dir = _populate_wave_dir(tmp_path, n_stations=1)
    (wave_dir / "scratch").mkdir()
    configurator = WW3Configurator(
        case_inputdir=tmp_path, boundaries=["west"], ww3_obc_product_name="none"
    )

    paths = configurator.get_output_filepaths(tmp_path / "ocnice")
    assert all(Path(p).is_file() for p in paths)
    assert "scratch" not in {Path(p).name for p in paths}


def test_output_filepaths_dir_matches_ww3_grid_inp_dir(tmp_path):
    """The reader, the writer and WW3_GRID_INP_DIR must all name one directory.

    configure() hands WW3_GRID_INP_DIR to CIME, process() writes there, and
    get_output_filepaths() reads there. Three call sites built that path
    independently before they were given a shared constant.
    """
    _populate_wave_dir(tmp_path, n_stations=1)
    configurator = WW3Configurator(
        case_inputdir=tmp_path, boundaries=["west"], ww3_obc_product_name="none"
    )
    # configure() ends in super().configure(), which applies each XML param
    # against a live CASEROOT. Only the value it sets matters here.
    with patch("CrocoDash.forcing.base.xmlchange"):
        configurator.configure()

    declared = Path(configurator.get_output_param("WW3_GRID_INP_DIR"))
    found = configurator.get_output_filepaths(tmp_path / "ocnice")
    assert found, "the wave dir was populated, so this must not be empty"
    assert {Path(p).parent for p in found} == {declared}


def _ww3_config(end_date="20200110", product="reference_waves"):
    return {
        "conditions": {"inputs": {"start_date": "20200101", "end_date": end_date}},
        "ww3": {"inputs": {"boundaries": ["west"], "ww3_obc_product_name": product}},
    }


@pytest.mark.parametrize(
    "previous, stale",
    [
        (_ww3_config(), False),
        (_ww3_config(end_date="20200105"), True),
        (_ww3_config(product="era5_wave_spectra"), True),
        ({}, True),
    ],
)
def test_ww3_staging_is_stale_once_its_inputs_or_the_dates_changed(
    tmp_path, previous, stale
):
    """process() skips the raw, regridded and merged files it finds in
    extract_forcings/ww3, and the merged ones carry no date -- so a new date
    range would rebuild the spectra from the old merge."""
    staging = tmp_path / "extract_forcings" / "ww3" / "merged"
    staging.mkdir(parents=True)
    configurator = WW3Configurator(
        case_inputdir=tmp_path, boundaries=["west"], ww3_obc_product_name="none"
    )
    result = configurator.stale_outputs(previous, _ww3_config(), tmp_path)
    assert result == ([staging.parent] if stale else [])
