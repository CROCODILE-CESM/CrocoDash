from pathlib import Path
from CrocoDash.extract_forcings import (
    regrid_dataset_piecewise as rb,
)
import pytest
from datetime import datetime
from CrocoDash.grid import Grid
from unittest.mock import patch, MagicMock
import numpy as np
import xarray as xr


@pytest.mark.slow
def test_regrid_data_piecewise_workflow(
    generate_piecewise_raw_data,
    dummy_forcing_factory,
    tmp_path,
    get_rect_grid_and_topo,
):

    # Get Grids
    grid, topo = get_rect_grid_and_topo

    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)
    topo_path = tmp_path / "topo.nc"
    topo.write_topo(topo_path)

    # Generate piecewise data
    piecewise_factory = generate_piecewise_raw_data
    bounds = Grid.get_bounding_boxes_of_rectangular_grid(grid)
    ds = dummy_forcing_factory(
        bounds["ic"]["lat_min"],
        bounds["ic"]["lat_max"],
        bounds["ic"]["lon_min"],
        bounds["ic"]["lon_max"],
    )
    directory_raw_data = Path(
        piecewise_factory(ds, "2020-01-01", "2020-01-31", "east_unprocessed_")
    )
    directory_raw_data = Path(
        piecewise_factory(ds, "2020-01-01", "2020-01-31", "south_unprocessed_")
    )

    # Setup other required variables
    output_folder = tmp_path / "output"
    output_folder.mkdir()
    varnames = {
        "time": "time",
        "yh": "latitude",
        "xh": "longitude",
        "zl": "depth",
        "eta": "zos",
        "u": "uo",
        "v": "vo",
        "tracers": {"salt": "so", "temp": "thetao"},
    }

    # Regrid data
    rb.regrid_dataset_piecewise(
        directory_raw_data,
        "(east|south)_(\\d{8})_(\\d{8})\\.nc",
        "%Y%m%d",
        "20200101",
        "20200106",
        hgrid_path,
        topo_path,
        None,
        varnames,
        output_folder,
        {"east": 1, "south": 2},
        run_initial_condition=False,
    )
    ## Check Output by checking the existence of two files, which checks the files are saved in the right place and of the correct date format ##
    for boundary_str in ["001", "002"]:
        for file_start_date, file_end_date in [("20200101", "20200106")]:
            assert (
                output_folder
                / "forcing_obc_segment_{}_{}_{}.nc".format(
                    boundary_str, file_start_date, file_end_date
                )
            ).exists()


def test_regrid_data_piecewise_parsing(
    generate_piecewise_raw_data,
    dummy_forcing_factory,
    tmp_path,
    get_rect_grid_and_topo,
    get_vgrid,
):

    # Get Grids
    grid, topo = get_rect_grid_and_topo
    vgrid = get_vgrid
    vgrid_path = tmp_path / "vgrid.nc"
    hgrid_path = tmp_path / "hgrid.nc"
    topo_path = tmp_path / "topo.nc"
    topo.write_topo(topo_path)
    grid.write_supergrid(hgrid_path)
    vgrid.write(vgrid_path)

    # Generate piecewise data
    piecewise_factory = generate_piecewise_raw_data
    bounds = Grid.get_bounding_boxes_of_rectangular_grid(grid)
    ds = dummy_forcing_factory(
        bounds["ic"]["lat_min"],
        bounds["ic"]["lat_max"],
        bounds["ic"]["lon_min"],
        bounds["ic"]["lon_max"],
    )
    directory_raw_data = Path(
        piecewise_factory(ds, "2020-01-01", "2020-01-31", "east_unprocessed_")
    )
    directory_raw_data = Path(
        piecewise_factory(ds, "2020-01-01", "2020-01-31", "south_unprocessed_")
    )
    ds.to_netcdf(directory_raw_data / "ic_unprocessed.nc")

    # Setup other required variables
    output_folder = tmp_path / "output"
    output_folder.mkdir()
    varnames = {
        "time": "time",
        "yh": "latitude",
        "xh": "longitude",
        "zl": "depth",
        "eta": "zos",
        "u": "uo",
        "v": "vo",
        "tracers": {"salt": "so", "temp": "thetao"},
    }

    # Regrid data
    preview_dict = rb.regrid_dataset_piecewise(
        directory_raw_data,
        "(east|south)_unprocessed_(\\d{8})_(\\d{8})\\.nc",
        "%Y%m%d",
        "20200101",
        "20200106",
        hgrid_path,
        topo_path,
        varnames,
        output_folder,
        {"east": 1, "south": 2},
        run_initial_condition=True,
        vgrid_path=vgrid_path,
        preview=True,
    )
    for boundary_str, name in [("001", "east"), ("002", "south")]:
        file_start_date = "20200101"
        file_end_date = "20200106"
        file_start, file_end, file_path = preview_dict["matching_files"][name][0]
        assert file_start == datetime.strptime(file_start_date, "%Y%m%d")
        assert file_end == datetime.strptime(file_end_date, "%Y%m%d")
        assert file_path == str(
            directory_raw_data
            / f"{name}_unprocessed_{file_start_date}_{file_end_date}.nc"
        )
        assert preview_dict["output_file_names"][
            0
        ] == "forcing_obc_segment_{}_{}_{}.nc".format(
            boundary_str, file_start_date, file_end_date
        ) or preview_dict[
            "output_file_names"
        ][
            1
        ] == "forcing_obc_segment_{}_{}_{}.nc".format(
            boundary_str, file_start_date, file_end_date
        )
    assert "init_eta_filled.nc" in preview_dict["output_file_names"]
    assert (
        directory_raw_data / "ic_unprocessed.nc"
        == preview_dict["matching_files"]["IC"][0][2]
    )
    new_output_folder = output_folder / "other_data"
    new_output_folder.mkdir()
    preview_dict = rb.regrid_dataset_piecewise(
        directory_raw_data,
        "(east|south)_unprocessed_(\\d{8})_(\\d{8})\\.nc",
        "%Y%m%d",
        "20200107",
        "20200131",
        hgrid_path,
        topo_path,
        varnames,
        new_output_folder,
        {"east": 1, "south": 2},
        run_initial_condition=False,
        preview=True,
    )
    for boundary_str in ["001", "002"]:
        file_start_date = "20200131"
        file_end_date = "20200131"
        assert (
            "forcing_obc_segment_{}_{}_{}.nc".format(
                boundary_str, file_start_date, file_end_date
            )
        ) in preview_dict["output_file_names"]
        file_start_date = "20200101"
        file_end_date = "20200106"
        assert (
            new_output_folder
            / "forcing_obc_segment_{}_{}_{}.nc".format(
                boundary_str, file_start_date, file_end_date
            )
        ) not in preview_dict["output_file_names"]


# =============================================================================
# Fast unit tests for small helpers
# =============================================================================


def test_final_cleanliness_fill_basic_2d():
    """Basic 2D fill: zeros become NaN then are filled along x and y."""
    da = xr.DataArray(
        np.array([[1.0, 0.0, 3.0], [0.0, 5.0, 0.0]]),
        dims=("ny", "nx"),
    )
    out = rb.final_cleanliness_fill(da, "nx", "ny")
    # All values should be finite (no NaNs) after forward/backward fill.
    assert np.all(np.isfinite(out.values))
    # Original non-zero values should be preserved.
    assert out.values[0, 0] == 1.0
    assert out.values[0, 2] == 3.0
    assert out.values[1, 1] == 5.0


def test_final_cleanliness_fill_with_z_dim():
    """With z_dim provided, the function should also ffill along z."""
    arr = np.array(
        [
            [[1.0, 0.0], [0.0, 2.0]],
            [[0.0, 0.0], [0.0, 0.0]],  # fully zero layer - must be filled from above
        ]
    )
    da = xr.DataArray(arr, dims=("zl", "ny", "nx"))
    out = rb.final_cleanliness_fill(da, "nx", "ny", "zl")
    assert np.all(np.isfinite(out.values))


def test_capture_fill_metadata_extracts_fill_and_missing_value():
    ds = xr.Dataset(
        {
            "a": (("x",), np.array([1.0, 2.0])),
            "b": (("x",), np.array([3.0, 4.0])),
            "c": (("x",), np.array([5.0, 6.0])),
        }
    )
    ds["a"].attrs["_FillValue"] = -1.0
    ds["a"].attrs["missing_value"] = -1.0
    ds["b"].attrs["_FillValue"] = -999.0
    # 'c' has no fill attrs and should be omitted from the result.
    meta = rb.capture_fill_metadata(ds)
    assert meta["a"] == {"_FillValue": -1.0, "missing_value": -1.0}
    assert meta["b"] == {"_FillValue": -999.0}
    assert "c" not in meta


def test_m6b_fill_missing_data_wrapper_raises():
    """Wrapper is skeleton code and must raise."""
    with pytest.raises(ValueError):
        rb.m6b_fill_missing_data_wrapper(ds=None, xdim=None, zdim=None, fill=None)


# =============================================================================
# Error-path tests for regrid_dataset_piecewise
# =============================================================================


def _standard_varnames():
    return {
        "time": "time",
        "yh": "latitude",
        "xh": "longitude",
        "zl": "depth",
        "eta": "zos",
        "u": "uo",
        "v": "vo",
        "tracers": {"salt": "so", "temp": "thetao"},
    }


def test_regrid_raises_if_vgrid_missing(tmp_path, get_rect_grid_and_topo):
    """run_initial_condition=True with non-existent vgrid_path must raise."""
    grid, topo = get_rect_grid_and_topo
    hgrid_path = tmp_path / "hgrid.nc"
    topo_path = tmp_path / "topo.nc"
    grid.write_supergrid(hgrid_path)
    topo.write_topo(topo_path)

    output_folder = tmp_path / "output"
    # Intentionally don't create output_folder; function should create it.
    with pytest.raises(FileNotFoundError):
        rb.regrid_dataset_piecewise(
            folder=tmp_path,
            input_dataset_regex="(east)_(\\d{8})_(\\d{8})\\.nc",
            date_format="%Y%m%d",
            start_date="20200101",
            end_date="20200106",
            hgrid_path=hgrid_path,
            bathymetry=topo_path,
            dataset_varnames=_standard_varnames(),
            output_folder=output_folder,
            boundary_number_conversion={"east": 1},
            run_initial_condition=True,
            run_boundary_conditions=False,
            vgrid_path=tmp_path / "nonexistent_vgrid.nc",
            preview=True,
        )


def test_regrid_returns_early_if_boundary_not_in_conversion(
    tmp_path,
    get_rect_grid_and_topo,
    dummy_forcing_factory,
    generate_piecewise_raw_data,
):
    """Boundary present in files but missing from boundary_number_conversion -> early return."""
    grid, topo = get_rect_grid_and_topo
    hgrid_path = tmp_path / "hgrid.nc"
    topo_path = tmp_path / "topo.nc"
    grid.write_supergrid(hgrid_path)
    topo.write_topo(topo_path)

    bounds = Grid.get_bounding_boxes_of_rectangular_grid(grid)
    ds = dummy_forcing_factory(
        bounds["ic"]["lat_min"],
        bounds["ic"]["lat_max"],
        bounds["ic"]["lon_min"],
        bounds["ic"]["lon_max"],
    )
    raw = Path(
        generate_piecewise_raw_data(ds, "2020-01-01", "2020-01-06", "east_unprocessed_")
    )

    output_folder = tmp_path / "output"
    output_folder.mkdir()

    # Conversion dict is missing 'east' -> function should log error and return None.
    result = rb.regrid_dataset_piecewise(
        folder=raw,
        input_dataset_regex="(east)_unprocessed_(\\d{8})_(\\d{8})\\.nc",
        date_format="%Y%m%d",
        start_date="20200101",
        end_date="20200106",
        hgrid_path=hgrid_path,
        bathymetry=topo_path,
        dataset_varnames=_standard_varnames(),
        output_folder=output_folder,
        boundary_number_conversion={"west": 1},  # deliberately wrong
        run_initial_condition=False,
        run_boundary_conditions=True,
        preview=True,
    )
    assert result is None


def test_regrid_raises_on_mom6_forge_fill_method(
    tmp_path,
    get_rect_grid_and_topo,
    dummy_forcing_factory,
    generate_piecewise_raw_data,
):
    """boundary_fill_method == 'mom6_forge' is marked not-yet-supported and must raise."""
    grid, topo = get_rect_grid_and_topo
    hgrid_path = tmp_path / "hgrid.nc"
    topo_path = tmp_path / "topo.nc"
    grid.write_supergrid(hgrid_path)
    topo.write_topo(topo_path)

    bounds = Grid.get_bounding_boxes_of_rectangular_grid(grid)
    ds = dummy_forcing_factory(
        bounds["ic"]["lat_min"],
        bounds["ic"]["lat_max"],
        bounds["ic"]["lon_min"],
        bounds["ic"]["lon_max"],
    )
    raw = Path(
        generate_piecewise_raw_data(ds, "2020-01-01", "2020-01-06", "east_unprocessed_")
    )

    varnames = _standard_varnames()
    varnames["boundary_fill_method"] = "mom6_forge"

    output_folder = tmp_path / "output"
    output_folder.mkdir()

    with pytest.raises(ValueError):
        rb.regrid_dataset_piecewise(
            folder=raw,
            input_dataset_regex="(east)_unprocessed_(\\d{8})_(\\d{8})\\.nc",
            date_format="%Y%m%d",
            start_date="20200101",
            end_date="20200106",
            hgrid_path=hgrid_path,
            bathymetry=topo_path,
            dataset_varnames=varnames,
            output_folder=output_folder,
            boundary_number_conversion={"east": 1},
            run_initial_condition=False,
            run_boundary_conditions=True,
            preview=True,
        )


def test_regrid_raises_on_unknown_fill_method(
    tmp_path,
    get_rect_grid_and_topo,
    dummy_forcing_factory,
    generate_piecewise_raw_data,
):
    """Unknown boundary_fill_method values must raise."""
    grid, topo = get_rect_grid_and_topo
    hgrid_path = tmp_path / "hgrid.nc"
    topo_path = tmp_path / "topo.nc"
    grid.write_supergrid(hgrid_path)
    topo.write_topo(topo_path)

    bounds = Grid.get_bounding_boxes_of_rectangular_grid(grid)
    ds = dummy_forcing_factory(
        bounds["ic"]["lat_min"],
        bounds["ic"]["lat_max"],
        bounds["ic"]["lon_min"],
        bounds["ic"]["lon_max"],
    )
    raw = Path(
        generate_piecewise_raw_data(ds, "2020-01-01", "2020-01-06", "east_unprocessed_")
    )

    varnames = _standard_varnames()
    varnames["boundary_fill_method"] = "not_a_real_method"

    output_folder = tmp_path / "output"
    output_folder.mkdir()

    with pytest.raises(ValueError):
        rb.regrid_dataset_piecewise(
            folder=raw,
            input_dataset_regex="(east)_unprocessed_(\\d{8})_(\\d{8})\\.nc",
            date_format="%Y%m%d",
            start_date="20200101",
            end_date="20200106",
            hgrid_path=hgrid_path,
            bathymetry=topo_path,
            dataset_varnames=varnames,
            output_folder=output_folder,
            boundary_number_conversion={"east": 1},
            run_initial_condition=False,
            run_boundary_conditions=True,
            preview=True,
        )


def test_regrid_skips_existing_obc_segment(
    tmp_path,
    get_rect_grid_and_topo,
    dummy_forcing_factory,
    generate_piecewise_raw_data,
):
    """If output file already exists, regridding should be skipped for that boundary file.

    We pre-create the expected output file with dates and confirm rm6.segment is never
    instantiated (if the skip branch works, there's nothing to regrid).
    """
    grid, topo = get_rect_grid_and_topo
    hgrid_path = tmp_path / "hgrid.nc"
    topo_path = tmp_path / "topo.nc"
    grid.write_supergrid(hgrid_path)
    topo.write_topo(topo_path)

    bounds = Grid.get_bounding_boxes_of_rectangular_grid(grid)
    ds = dummy_forcing_factory(
        bounds["ic"]["lat_min"],
        bounds["ic"]["lat_max"],
        bounds["ic"]["lon_min"],
        bounds["ic"]["lon_max"],
    )
    raw = Path(
        generate_piecewise_raw_data(ds, "2020-01-01", "2020-01-06", "east_unprocessed_")
    )

    output_folder = tmp_path / "output"
    output_folder.mkdir()
    # Pre-create the file that the regridder would otherwise write.
    (output_folder / "forcing_obc_segment_001_20200101_20200106.nc").write_text("x")

    with patch(
        "CrocoDash.extract_forcings.regrid_dataset_piecewise.rm6.segment"
    ) as mock_seg:
        rb.regrid_dataset_piecewise(
            folder=raw,
            input_dataset_regex="(east)_unprocessed_(\\d{8})_(\\d{8})\\.nc",
            date_format="%Y%m%d",
            start_date="20200101",
            end_date="20200106",
            hgrid_path=hgrid_path,
            bathymetry=topo_path,
            dataset_varnames=_standard_varnames(),
            output_folder=output_folder,
            boundary_number_conversion={"east": 1},
            run_initial_condition=False,
            run_boundary_conditions=True,
            preview=False,
        )
    # Skip branch hit: segment should never be constructed.
    assert mock_seg.call_count == 0


# =============================================================================
# Mocked IC-pipeline test (large coverage gain)
# =============================================================================


def _write_init_files(folder, z=3, ny=4, nx=5):
    """Write dummy init_eta.nc / init_vel.nc / init_tracers.nc files that mirror
    what expt.setup_initial_condition would produce, so the fill pipeline runs.

    NOTE: The source code iterates `for z_ind in range(ds[z_act].shape[0])` and
    then does `ds["u"][z_ind] = ...`, which indexes on the *first* dim of the
    variable. So the variables must have `zl` as the first dim.
    """
    folder = Path(folder)
    eta = xr.Dataset({"eta_t": (("ny", "nx"), np.ones((ny, nx), dtype="f4"))})
    eta.to_netcdf(folder / "init_eta.nc")

    vel = xr.Dataset(
        {
            "u": (("zl", "ny", "nxp"), np.ones((z, ny, nx + 1), dtype="f4")),
            "v": (("zl", "nyp", "nx"), np.ones((z, ny + 1, nx), dtype="f4")),
            "zl": (("zl",), np.arange(z, dtype="f4")),
        }
    )
    vel.to_netcdf(folder / "init_vel.nc")

    tr = xr.Dataset(
        {
            "temp": (("zl", "ny", "nx"), np.ones((z, ny, nx), dtype="f4")),
            "salt": (("zl", "ny", "nx"), np.ones((z, ny, nx), dtype="f4")),
            "zl": (("zl",), np.arange(z, dtype="f4")),
        }
    )
    tr.to_netcdf(folder / "init_tracers.nc")


def test_regrid_ic_pipeline_mocked(
    tmp_path,
    get_rect_grid_and_topo,
    get_vgrid,
    dummy_forcing_factory,
    generate_piecewise_raw_data,
):
    """Exercise the full non-preview IC fill pipeline with heavy deps mocked out."""
    grid, topo = get_rect_grid_and_topo
    vgrid = get_vgrid
    hgrid_path = tmp_path / "hgrid.nc"
    topo_path = tmp_path / "topo.nc"
    vgrid_path = tmp_path / "vgrid.nc"
    grid.write_supergrid(hgrid_path)
    topo.write_topo(topo_path)
    vgrid.write(vgrid_path)

    bounds = Grid.get_bounding_boxes_of_rectangular_grid(grid)
    ds = dummy_forcing_factory(
        bounds["ic"]["lat_min"],
        bounds["ic"]["lat_max"],
        bounds["ic"]["lon_min"],
        bounds["ic"]["lon_max"],
    )
    raw = Path(
        generate_piecewise_raw_data(ds, "2020-01-01", "2020-01-06", "east_unprocessed_")
    )
    # The IC logic looks for folder/ic_unprocessed.nc
    ds.to_netcdf(raw / "ic_unprocessed.nc")

    output_folder = tmp_path / "output"
    output_folder.mkdir()

    # Build a mock expt returned by rm6.experiment.create_empty().
    # setup_initial_condition must produce the init_*.nc files the fill pipeline reads.
    mock_expt = MagicMock()
    mock_expt.mom_input_dir = output_folder
    mock_expt._make_vgrid = MagicMock(return_value=MagicMock())
    mock_expt.setup_initial_condition = MagicMock(
        side_effect=lambda *a, **kw: _write_init_files(output_folder)
    )

    # fill_missing_data passes arrays through unchanged; this keeps shapes valid.
    def _passthrough(arr, mask):
        return arr

    with patch(
        "CrocoDash.extract_forcings.regrid_dataset_piecewise.rm6.experiment.create_empty",
        return_value=mock_expt,
    ), patch(
        "CrocoDash.extract_forcings.regrid_dataset_piecewise.m6b.utils.fill_missing_data",
        side_effect=_passthrough,
    ):
        rb.regrid_dataset_piecewise(
            folder=raw,
            input_dataset_regex="(east)_unprocessed_(\\d{8})_(\\d{8})\\.nc",
            date_format="%Y%m%d",
            start_date="20200101",
            end_date="20200106",
            hgrid_path=hgrid_path,
            bathymetry=topo_path,
            dataset_varnames=_standard_varnames(),
            output_folder=output_folder,
            boundary_number_conversion={"east": 1},
            run_initial_condition=True,
            run_boundary_conditions=False,  # keep test focused on IC pipeline
            vgrid_path=vgrid_path,
            preview=False,
        )

    assert (output_folder / "init_eta_filled.nc").exists()
    assert (output_folder / "init_vel_filled.nc").exists()
    assert (output_folder / "init_tracers_filled.nc").exists()
    mock_expt.setup_initial_condition.assert_called_once()


def test_regrid_ic_pipeline_mocked_skips_existing(
    tmp_path,
    get_rect_grid_and_topo,
    get_vgrid,
    dummy_forcing_factory,
    generate_piecewise_raw_data,
):
    """If init_eta_filled.nc already exists, the fill pipeline is skipped."""
    grid, topo = get_rect_grid_and_topo
    vgrid = get_vgrid
    hgrid_path = tmp_path / "hgrid.nc"
    topo_path = tmp_path / "topo.nc"
    vgrid_path = tmp_path / "vgrid.nc"
    grid.write_supergrid(hgrid_path)
    topo.write_topo(topo_path)
    vgrid.write(vgrid_path)

    bounds = Grid.get_bounding_boxes_of_rectangular_grid(grid)
    ds = dummy_forcing_factory(
        bounds["ic"]["lat_min"],
        bounds["ic"]["lat_max"],
        bounds["ic"]["lon_min"],
        bounds["ic"]["lon_max"],
    )
    raw = Path(
        generate_piecewise_raw_data(ds, "2020-01-01", "2020-01-06", "east_unprocessed_")
    )
    ds.to_netcdf(raw / "ic_unprocessed.nc")

    output_folder = tmp_path / "output"
    output_folder.mkdir()
    # Both init_eta.nc AND init_eta_filled.nc exist -> both "skip" branches taken.
    (output_folder / "init_eta.nc").write_text("x")
    (output_folder / "init_eta_filled.nc").write_text("x")

    mock_expt = MagicMock()
    mock_expt.mom_input_dir = output_folder
    mock_expt._make_vgrid = MagicMock(return_value=MagicMock())

    with patch(
        "CrocoDash.extract_forcings.regrid_dataset_piecewise.rm6.experiment.create_empty",
        return_value=mock_expt,
    ):
        rb.regrid_dataset_piecewise(
            folder=raw,
            input_dataset_regex="(east)_unprocessed_(\\d{8})_(\\d{8})\\.nc",
            date_format="%Y%m%d",
            start_date="20200101",
            end_date="20200106",
            hgrid_path=hgrid_path,
            bathymetry=topo_path,
            dataset_varnames=_standard_varnames(),
            output_folder=output_folder,
            boundary_number_conversion={"east": 1},
            run_initial_condition=True,
            run_boundary_conditions=False,
            vgrid_path=vgrid_path,
            preview=False,
        )

    # setup_initial_condition should NOT be called because init_eta.nc already exists.
    mock_expt.setup_initial_condition.assert_not_called()
