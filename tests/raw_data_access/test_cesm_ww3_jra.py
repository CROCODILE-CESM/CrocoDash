"""Tests for the CESM-WW3-JRA product.

Everything here runs against a fabricated 4x6 "database" with a 2x4 spectrum
(8 `va` variables instead of 600), built by the fixtures below. That keeps
the conventions -- the reshape order, the action/energy conversion, the
direction axis and its order, the NO_LEAP mapping -- checkable against
closed-form answers, which is exactly what a real restart cannot give you.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from netCDF4 import Dataset

from CrocoDash.raw_data_access.base import DIRECTION_TO, LAND_NAN, WW3ForcingProduct
from CrocoDash.raw_data_access.registry import ProductRegistry
from CrocoDash.raw_data_access.datasets.cesm_ww3_jra import (
    _DEFAULT_DATABASE_ROOT,
    _DEFAULT_GRID_FILE,
    CESM_WW3_JRA,
    action_to_energy,
    available_range,
    discover_case_name,
    group_velocity,
    requested_timestamps,
    restart_filename,
    spectral_axes,
)

CASE = "fake_jra.glo.001"
NY, NX, NK, NTH = 4, 6, 2, 4
NSPEC = NK * NTH
FR1, XFR = 0.1, 1.1
# Cell centres: lon 0.5..5.5 on a 6-cell cyclic axis, lat -1.5..1.5.
LONS = 0.5 + np.arange(NX, dtype=float)
LATS = -1.5 + np.arange(NY, dtype=float)
DEPTH = 1000.0
# One land column so the land -> 0 path is always exercised.
LAND_I = 3


def _va_value(j, i, s):
    """A distinct, reproducible action density per (cell, spectral bin)."""
    return 1.0 + j + 10.0 * i + 100.0 * s


def _write_restart(path, stamp, scale=1.0):
    with Dataset(path, "w", format="NETCDF3_64BIT_DATA") as nc:
        nc.createDimension("time", None)
        nc.createDimension("ny", NY)
        nc.createDimension("nx", NX)
        t = nc.createVariable("time", "f8", ("time",))
        t.units = "seconds since 2018-11-01 00:00:00"
        t.calendar = "noleap"
        t[0] = 0.0
        for name, value in (("nk", NK), ("nth", NTH)):
            v = nc.createVariable(name, "i4")
            v[...] = value

        land = np.zeros((NY, NX), dtype=bool)
        land[:, LAND_I] = True
        for s in range(NSPEC):
            v = nc.createVariable(
                f"va{s + 1:04d}",
                "f4",
                ("time", "ny", "nx"),
                fill_value=np.float32(9.96921e36),
            )
            block = np.array(
                [[_va_value(j, i, s) * scale for i in range(NX)] for j in range(NY)],
                dtype=np.float32,
            )
            block[land] = 9.96921e36
            v[0, :, :] = block
        m = nc.createVariable(
            "mapsta", "i4", ("time", "ny", "nx"), fill_value=np.int32(-2147483647)
        )
        mapsta = np.ones((NY, NX), dtype=np.int32)
        mapsta[land] = -2147483647
        m[0, :, :] = mapsta


def _write_grid(path, ny=NY, depth=DEPTH, attrs=None):
    x, y = np.meshgrid(LONS, LATS[:ny])
    depth = np.full((ny, NX), depth)
    mask = np.ones((ny, NX), dtype=np.int32)
    mask[:, LAND_I] = 0
    depth[:, LAND_I] = 0.0
    ds = xr.Dataset(
        {
            "x": (("ny", "nx"), x),
            "y": (("ny", "nx"), y),
            "depth": (("ny", "nx"), depth),
            "mask": (("ny", "nx"), mask),
        },
        attrs={"min_depth": 10.0} if attrs is None else attrs,
    )
    ds.to_netcdf(path)


@pytest.fixture
def database(tmp_path):
    """A 4-day fake database spanning a leap day: 2020-02-27 .. 2020-03-01.

    The database itself is NO_LEAP, so it has no 02-29 -- that absence is
    the point of the fixture.
    """
    root = tmp_path / "run"
    root.mkdir()
    grid = tmp_path / "ocean_topog_fake.nc"
    _write_grid(grid)
    for day in ("2020-02-27", "2020-02-28", "2020-03-01", "2020-03-02"):
        for hour, seconds in ((0, 0), (6, 21600), (12, 43200), (18, 64800)):
            _write_restart(
                root / f"{CASE}.ww3.r.{day}-{seconds:05d}.nc",
                f"{day}T{hour:02d}",
                # Make every snapshot distinguishable, so "served 02-28's
                # data" is a real assertion rather than a coincidence.
                scale=1.0 + 0.01 * (int(day[-2:]) + hour),
            )
    return root, grid


def _extract(database, **kwargs):
    root, grid = database
    args = dict(
        dates=["2020-02-27", "2020-02-27"],
        lat_min=-1.0,
        lat_max=1.0,
        lon_min=1.0,
        lon_max=4.0,
        database_root=str(root),
        grid_file=str(grid),
        fr1=FR1,
        xfr=XFR,
    )
    args.update(kwargs)
    args.setdefault("output_folder", root.parent / "out")
    args.setdefault("output_filename", "spectra.nc")
    path = CESM_WW3_JRA.get_cesm_ww3_jra_spectra(**args)
    return xr.open_dataset(path)


# --------------------------------------------------------------------------
# Pure conversions
# --------------------------------------------------------------------------


def test_spectral_axes_frequency_is_geometric():
    frequency, sigma, _ = spectral_axes(5, 4, fr1=0.04118, xfr=1.1)
    assert frequency[0] == pytest.approx(0.04118)
    assert frequency == pytest.approx(0.04118 * 1.1 ** np.arange(5))
    assert sigma == pytest.approx(2 * np.pi * frequency)


def test_spectral_axes_direction_is_to_in_ww3_index_order():
    # th = 0, 15, ..., 345 (CCW from east) -> mod(450 - th, 360).
    _, _, direction = spectral_axes(2, 24)
    assert direction[0] == pytest.approx(90.0)  # th=0 (eastward) -> "to" 90
    assert direction[1] == pytest.approx(75.0)
    assert direction[6] == pytest.approx(0.0)  # th=90 (northward) -> "to" 0
    assert direction[-1] == pytest.approx(105.0)
    # The order is deliberately NOT sorted -- see convention 5.
    assert not np.all(np.diff(direction) > 0)
    assert sorted(direction) == pytest.approx(np.arange(24) * 15.0)


def test_group_velocity_deep_and_shallow_limits():
    sigma = np.array([2 * np.pi * 0.1])
    deep = group_velocity(sigma, np.array([10000.0]))
    assert deep[0, 0] == pytest.approx(0.5 * 9.806 / sigma[0], rel=1e-6)

    # Shallow water: Cg -> sqrt(g*d) as kd -> 0.
    shallow = group_velocity(np.array([2 * np.pi * 0.005]), np.array([2.0]))
    assert shallow[0, 0] == pytest.approx(np.sqrt(9.806 * 2.0), rel=1e-3)


def test_group_velocity_is_finite_over_abyssal_depths():
    """kd reaches ~3000 for the shortest bin over 6 km of water, which
    overflows cosh/sinh unless it is clamped."""
    _, sigma, _ = spectral_axes(25, 24)
    cg = group_velocity(sigma, np.full((3, 4), 6000.0))
    assert np.all(np.isfinite(cg))
    assert np.all(cg > 0)


def test_action_to_energy_matches_the_documented_formula():
    va = np.arange(6, dtype=float).reshape(1, 3, 2)  # (..., nk=3, nth=2)
    sigma = np.array([1.0, 2.0, 3.0])
    cg = np.array([[4.0, 5.0, 6.0]])
    energy = action_to_energy(va, sigma, cg)
    assert energy == pytest.approx(va * (2 * np.pi * sigma / cg)[..., None])


# --------------------------------------------------------------------------
# Time axis and file naming
# --------------------------------------------------------------------------


def test_requested_timestamps_covers_whole_days_at_both_ends():
    stamps = requested_timestamps(["2019-03-01", "2019-03-02"])
    assert len(stamps) == 8
    assert stamps[0] == pd.Timestamp("2019-03-01 00:00")
    assert stamps[-1] == pd.Timestamp("2019-03-02 18:00")


def test_requested_timestamps_single_day_keeps_all_four_steps():
    stamps = requested_timestamps(["2019-03-01", "2019-03-01"])
    assert list(stamps.hour) == [0, 6, 12, 18]


def test_restart_filename_formats_seconds_of_day():
    assert restart_filename("c", "2019-06-05 00:00") == "c.ww3.r.2019-06-05-00000.nc"
    assert restart_filename("c", "2019-06-05 06:00") == "c.ww3.r.2019-06-05-21600.nc"
    assert restart_filename("c", "2019-06-05 18:00") == "c.ww3.r.2019-06-05-64800.nc"


def test_restart_filename_maps_the_leap_day_onto_february_28():
    assert restart_filename("c", "2020-02-29 12:00") == "c.ww3.r.2020-02-28-43200.nc"
    # Only 02-29 is remapped; its neighbours are untouched.
    assert restart_filename("c", "2020-03-01 12:00") == "c.ww3.r.2020-03-01-43200.nc"


def test_discover_case_name_and_range(database):
    root, _ = database
    assert discover_case_name(root) == CASE
    first, last = available_range(root, CASE)
    assert first == pd.Timestamp("2020-02-27 00:00")
    assert last == pd.Timestamp("2020-03-02 18:00")


def test_discover_case_name_rejects_a_mixed_directory(database, tmp_path):
    root, _ = database
    (root / "other.ww3.r.2020-02-27-00000.nc").write_bytes(b"")
    with pytest.raises(ValueError, match="more than one case"):
        discover_case_name(root)


def test_discover_case_name_rejects_an_empty_directory(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match="No WW3 restart files"):
        discover_case_name(empty)


# --------------------------------------------------------------------------
# End to end
# --------------------------------------------------------------------------


def test_output_has_the_shape_the_ww3_pipeline_expects(database):
    ds = _extract(database)
    # forcing/ww3.py::_extract_all_stations takes the single data variable by
    # position and requires exactly these dims.
    assert list(ds.data_vars) == ["efth"]
    assert set(ds["efth"].dims) == {
        "time",
        "latitude",
        "longitude",
        "frequency",
        "direction",
    }
    assert ds.sizes["time"] == 4
    assert ds.sizes["frequency"] == NK
    assert ds.sizes["direction"] == NTH
    assert ds["time"].dtype == np.dtype("datetime64[ns]")


def test_values_match_the_analytic_conversion(database):
    ds = _extract(database)
    frequency, sigma, _ = spectral_axes(NK, NTH, fr1=FR1, xfr=XFR)
    cg = group_velocity(sigma, np.array([DEPTH]))[0]

    lon = float(ds["longitude"][1])
    lat = float(ds["latitude"][1])
    i = int(np.argmin(np.abs(LONS - lon)))
    j = int(np.argmin(np.abs(LATS - lat)))

    scale = 1.0 + 0.01 * (27 + 0)  # 2020-02-27 00Z
    got = ds["efth"].isel(time=0, latitude=1, longitude=1).values
    for ik in range(NK):
        for ith in range(NTH):
            # Convention 1: frequency-major, kk = (ik-1)*nth + ith.
            s = ik * NTH + ith
            expected = _va_value(j, i, s) * scale * 2 * np.pi * sigma[ik] / cg[ik]
            assert got[ik, ith] == pytest.approx(expected, rel=1e-5)


def test_land_cells_are_nan_not_zero(database):
    """Land must stay distinguishable from a sea point carrying no energy:
    an ice-covered boundary is all zeros and has to survive as real
    stations. forcing/ww3.py drops the NaN ones and keeps the zeros."""
    ds = _extract(database, lon_min=1.0, lon_max=5.0)
    land = ds["efth"].sel(longitude=LONS[LAND_I]).values
    assert np.isnan(land).all()
    # Every wet cell is finite, so NaN means land and nothing else.
    wet = ds["efth"].drop_sel(longitude=LONS[LAND_I]).values
    assert np.isfinite(wet).all()
    assert (wet > 0).any()


def test_an_all_zero_sea_point_is_kept_as_a_station(database, tmp_path):
    """The Bering Sea case: WW3 has iced the cell over, so every bin is
    exactly zero, but it is still water and still a boundary condition."""
    root, grid = database
    # Zero one wet column in every snapshot, the way ice dissipation would.
    for restart in sorted(root.glob(f"{CASE}.ww3.r.*.nc")):
        with Dataset(restart, "a") as nc:
            for s in range(NSPEC):
                block = nc.variables[f"va{s + 1:04d}"][0, :, :]
                block[:, 1] = 0.0
                nc.variables[f"va{s + 1:04d}"][0, :, :] = block

    ds = _extract(database, lon_min=1.0, lon_max=5.0)
    iced = ds["efth"].sel(longitude=LONS[1]).values
    assert np.all(iced == 0.0)
    assert not np.isnan(iced).any()  # zero, not land


def test_direction_axis_is_emitted_in_ww3_index_order(database):
    ds = _extract(database)
    assert ds["direction"].values == pytest.approx([90.0, 0.0, 270.0, 180.0])


def test_leap_day_is_served_by_february_28_under_its_own_stamp(database):
    ds = _extract(database, dates=["2020-02-28", "2020-03-01"])
    stamps = pd.to_datetime(ds["time"].values)
    assert len(stamps) == 12
    assert pd.Timestamp("2020-02-29 06:00") in set(stamps)

    feb28 = ds.sel(time="2020-02-28")["efth"].values
    feb29 = ds.sel(time="2020-02-29")["efth"].values
    # assert_array_equal, not approx: land is NaN and NaN == NaN has to hold
    # here, since "served 02-28's file" means bit-for-bit, land included.
    np.testing.assert_array_equal(feb29, feb28)
    # ... and 03-01 is its own day, not another copy.
    mar01 = ds.sel(time="2020-03-01")["efth"].values
    wet = np.isfinite(feb28)
    assert not np.allclose(mar01[wet], feb28[wet])


def test_non_leap_years_are_unaffected(database, tmp_path):
    ds = _extract(database, dates=["2020-02-27", "2020-02-28"])
    stamps = pd.to_datetime(ds["time"].values)
    assert len(stamps) == 8
    assert not any((s.month, s.day) == (2, 29) for s in stamps)


def test_window_crossing_the_cyclic_seam_stays_monotonic(database):
    """A window spanning the 0/360 seam is read as two hyperslabs and
    reassembled; its longitudes stay increasing so the consumer's own
    wrapping has something sane to work with."""
    ds = _extract(database, lon_min=4.5, lon_max=361.0)
    lons = ds["longitude"].values
    assert np.all(np.diff(lons) > 0)
    assert (lons % 360.0 == 0.5).any() and (lons % 360.0 == 5.5).any()
    # The seam is a join, not a gap: values still come from the right cells.
    for lon in lons:
        i = int(round((lon - 0.5))) % NX
        if i == LAND_I:
            continue
        assert (
            float(
                ds["efth"]
                .sel(longitude=lon)
                .isel(time=0, latitude=0, frequency=0, direction=0)
            )
            > 0
        )


@pytest.mark.parametrize(
    "lon_min, lon_max",
    [(0.0, 360.0), (10.0, 370.0), (0.1, 360.1), (10.3, 370.3), (-10.0, 360.0)],
)
def test_a_full_turn_of_longitude_reads_every_column(database, lon_min, lon_max):
    """A full turn wraps its ends onto (nearly) the same longitude -- only
    exactly so for integer pairs; it must read the whole circle, not
    collapse to the few columns around lon_min."""
    ds = _extract(database, lon_min=lon_min, lon_max=lon_max)
    assert ds.sizes["longitude"] == NX


def test_a_grid_file_of_another_shape_is_rejected(database, tmp_path):
    """Indices computed on the wrong grid would still be in range for a
    larger restart and silently read the wrong cells."""
    grid = tmp_path / "other_topog.nc"
    _write_grid(grid, ny=NY - 1)
    with pytest.raises(ValueError, match="grid_file"):
        _extract(database, grid_file=str(grid))


@pytest.mark.parametrize("lon_max", [361.0, 1.0], ids=["ascending", "descending"])
def test_a_descending_pair_reads_eastward_across_the_seam(database, lon_max):
    """359..1 is the same 2-degree window as 359..361 -- 4 of the 6 columns
    without padding. Reading a descending pair as a full turn would give 6."""
    ds = _extract(
        database,
        lon_min=359.0,
        lon_max=lon_max,
        buffer_deg=0.0,
        max_buffer_deg=0.0,
    )
    assert ds.sizes["longitude"] == 4


@pytest.mark.parametrize("attrs", [{}, {"min_depth": 0.0}], ids=["missing", "zero"])
def test_a_grid_file_without_a_positive_min_depth_floors_at_its_shallowest_wet_depth(
    database, tmp_path, caplog, attrs
):
    """Zero is common (the tutorial's Topo uses min_depth=0); that grid has
    to work."""
    grid = tmp_path / "no_min_depth.nc"
    _write_grid(grid, attrs=attrs)
    with caplog.at_level("WARNING"):
        ds = _extract(database, grid_file=str(grid))
    assert "shallowest wet depth" in caplog.text
    assert np.isfinite(ds["efth"].drop_sel(longitude=LONS[LAND_I]).values).all()


def test_a_grid_file_with_no_positive_depth_is_named_in_the_error(database, tmp_path):
    grid = tmp_path / "all_land.nc"
    _write_grid(grid, depth=0.0, attrs={})
    with pytest.raises(ValueError, match="all_land.nc has no positive depth"):
        _extract(database, grid_file=str(grid))


@pytest.mark.filterwarnings("error::RuntimeWarning")
def test_energy_overflowing_float32_is_an_error_not_inf(database, tmp_path):
    """A near-zero depth gives a finite float64 energy that overflows the
    float32 store; inf is not land, so it would reach ww3_bounc. The error
    has to surface even under -W error, not the cast's overflow warning."""
    grid = tmp_path / "shallow_topog.nc"
    _write_grid(grid, depth=1e-300, attrs={"min_depth": 1e-300})
    with pytest.raises(ValueError, match="not finite in float32"):
        _extract(database, grid_file=str(grid), lon_min=1.0, lon_max=2.0)


def test_a_fill_value_at_a_sea_cell_is_blamed_on_the_mask(database):
    """The wet mask comes from the first restart; a later one with a fill
    value where that mask says sea is a mask disagreement, not a depth
    problem."""
    root, _ = database
    with Dataset(root / f"{CASE}.ww3.r.2020-02-27-21600.nc", "a") as nc:
        nc.variables["va0001"][0, 1, 1] = np.float32(9.96921e36)
    with pytest.raises(ValueError, match="disagree on the land mask"):
        _extract(database)


def test_dates_outside_the_database_are_rejected(database):
    with pytest.raises(ValueError, match="covers"):
        _extract(database, dates=["2020-02-25", "2020-02-26"])
    with pytest.raises(ValueError, match="covers"):
        _extract(database, dates=["2020-03-02", "2020-03-05"])


def test_a_thin_boundary_strip_still_finds_stations(database):
    """A "north" boundary box is a near-zero-height strip; on a coarse
    database it can contain no cell centre at all, so the window has to
    grow until it does."""
    ds = _extract(database, lat_min=0.02, lat_max=0.04, lon_min=1.0, lon_max=2.0)
    wet = (ds["efth"].values > 0).any(axis=(0, 3, 4))
    assert wet.sum() >= 2


def test_all_land_window_raises_rather_than_returning_zeros(database):
    """Pinned to the one land column, with the padding disabled so it cannot
    escape: better a loud failure than a boundary forced by zeros."""
    with pytest.raises(ValueError, match="No wet database cells"):
        _extract(
            database,
            lat_min=-0.5,
            lat_max=-0.5,
            lon_min=LONS[LAND_I],
            lon_max=LONS[LAND_I],
            buffer_deg=0.0,
            max_buffer_deg=0.0,
        )


def test_latitudes_outside_the_database_are_reported_as_such(database):
    with pytest.raises(ValueError, match="lies entirely outside"):
        _extract(database, lat_min=88.0, lat_max=89.0)


def test_a_missing_restart_is_reported_not_silently_skipped(database):
    root, _ = database
    (root / f"{CASE}.ww3.r.2020-02-28-43200.nc").unlink()
    with pytest.raises(FileNotFoundError, match="missing"):
        _extract(database, dates=["2020-02-27", "2020-03-01"])


# --------------------------------------------------------------------------
# Product registration / metadata
# --------------------------------------------------------------------------


def test_product_is_registered_case_insensitively():
    ProductRegistry.load()
    assert ProductRegistry.product_exists("CESM-WW3-JRA")
    assert ProductRegistry.product_exists("cesm-ww3-jra")
    assert ProductRegistry.get_product("CESM-WW3-JRA") is CESM_WW3_JRA


def test_product_is_a_ww3_forcing_product_declaring_the_to_convention():
    ProductRegistry.load()
    assert ProductRegistry.product_is_of_type("CESM-WW3-JRA", WW3ForcingProduct)
    assert CESM_WW3_JRA.direction_convention == DIRECTION_TO
    assert CESM_WW3_JRA.land_marker == LAND_NAN


@pytest.mark.skipif(
    not (Path(_DEFAULT_DATABASE_ROOT).is_dir() and Path(_DEFAULT_GRID_FILE).is_file()),
    reason="production database and grid file are on GLADE scratch",
)
def test_registry_toy_call_is_inside_the_database():
    """The generic toy dates (2000) predate the database, which made the
    registry-wide validation test fail on this product."""
    assert ProductRegistry.validate_function("cesm-ww3-jra", "get_cesm_ww3_jra_spectra")


def test_write_metadata_has_required_fields():
    metadata = CESM_WW3_JRA.write_metadata()
    missing = [f for f in CESM_WW3_JRA.required_metadata if f not in metadata]
    assert not missing, f"Missing required metadata: {missing}"
    assert "get_cesm_ww3_jra_spectra" in CESM_WW3_JRA._access_methods
