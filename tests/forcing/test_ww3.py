"""Tests for WW3Configurator and its process()-adjacent helpers."""

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from CrocoDash.forcing import ww3
from CrocoDash.forcing.base import WorkflowContext
from CrocoDash.forcing.ww3 import WAVE_SUBDIR, WW3Configurator
from CrocoDash.raw_data_access.base import WW3ForcingProduct, accessmethod, GREGORIAN


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


def test_process_ww3_obc_skipped_without_product(tmp_path, gen_grid_topo_vgrid):
    """Boundary spectra are opt-in: with neither product nor function named,
    process() must generate nothing at all rather than fall back to a default
    product. WW3 runs fine unforced at its boundaries, and defaulting to ERA5
    would make every WW3 case need a CDS API key."""
    grid, topo, vgrid = gen_grid_topo_vgrid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)

    configurator = WW3Configurator(case_inputdir=tmp_path, boundaries=["west"])

    with patch("CrocoDash.forcing.ww3.obc.process_obc_conditions") as mock_process:
        configurator.process(_make_ctx(tmp_path, supergrid_path=hgrid_path))

    mock_process.assert_not_called()

    # No spec.list / ww3_bounc.nml / point files -- but WW3_GRID_INP_DIR still
    # has to name a directory that exists, since CIME's ww3 buildnml reads it.
    wave_dir = tmp_path / "wave"
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
def test_process_ww3_obc_half_specified_raises(
    tmp_path, gen_grid_topo_vgrid, kwargs, given, missing
):
    """Only one of the pair given is a typo or a forgotten argument, not a
    request to skip -- skipping silently would hide it behind a case that
    still runs."""
    grid, topo, vgrid = gen_grid_topo_vgrid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)

    configurator = WW3Configurator(
        case_inputdir=tmp_path, boundaries=["west"], **kwargs
    )

    with patch("CrocoDash.forcing.ww3.obc.process_obc_conditions") as mock_process:
        with pytest.raises(ValueError, match=f"{given} was given but {missing}"):
            configurator.process(_make_ctx(tmp_path, supergrid_path=hgrid_path))

    mock_process.assert_not_called()


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


def test_regrid_chunk_era5_writes_all_stations(tmp_path):
    ds = _make_synthetic_era5_window(n_stations=3)

    ww3._regrid_chunk_era5(
        ds=ds,
        hgrid=None,
        boundary="west",
        seg_id=3,
        outfolder=tmp_path,
        dataset_varnames={},
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
        lons = np.linspace(lon_min, lon_max, n_stations)
        lats = np.array([(lat_min + lat_max) / 2])
        efth = np.zeros((len(time), 1, n_stations, len(freq), len(direction)))
        for k in range(n_stations):
            efth[:, 0, k, :, :] = 100.0 + k

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

    wave = tmp_path / "wave"
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

    wave = tmp_path / "wave"
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


# =============================================================================
# validate_args / smoke
# =============================================================================


def test_ww3_configurator_defaults_to_none_product():
    # None (unset) means "skip boundary spectra entirely" (handled in
    # process()) -- a valid WW3 configuration, not something validate_args
    # should reject.
    WW3Configurator(case_inputdir="dummy", boundaries=["west"])


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
    )
    WW3Configurator(
        case_inputdir="dummy",
        boundaries=["west"],
        ww3_obc_product_name="reference_waves",
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
    configurator = WW3Configurator(case_inputdir=tmp_path, boundaries=["west"])
    assert configurator.get_output_filepaths(tmp_path / "ocnice") == []


def test_get_output_filepaths_returns_every_generated_file(tmp_path):
    """Spectra count is not known up front, so this globs rather than names."""
    _populate_wave_dir(tmp_path, n_stations=3)
    configurator = WW3Configurator(case_inputdir=tmp_path, boundaries=["west"])

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
    configurator = WW3Configurator(case_inputdir=tmp_path, boundaries=["west"])

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
    configurator = WW3Configurator(case_inputdir=tmp_path, boundaries=["west"])
    # configure() ends in super().configure(), which applies each XML param
    # against a live CASEROOT. Only the value it sets matters here.
    with patch("CrocoDash.forcing.base.xmlchange"):
        configurator.configure()

    declared = Path(configurator.get_output_param("WW3_GRID_INP_DIR"))
    found = configurator.get_output_filepaths(tmp_path / "ocnice")
    assert found, "the wave dir was populated, so this must not be empty"
    assert {Path(p).parent for p in found} == {declared}
