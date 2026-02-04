import regional_mom6 as rm6
from pathlib import Path
from CrocoDash import logging
from CrocoDash.extract_forcings.utils import (
    parse_dataset_folder,
    check_date_continuity,
)
import re
import os
from collections import defaultdict
from datetime import datetime
import xarray as xr
import mom6_bathy as m6b
import numpy as np
from CrocoDash.topo import Topo
from CrocoDash.grid import Grid
import netCDF4

logger = logging.setup_logger(__name__)


def regrid_dataset_piecewise(
    folder: str | Path,
    input_dataset_regex: str,
    date_format: str,
    start_date: str,
    end_date: str,
    hgrid_path: str | Path,
    bathymetry: str | Path,
    dataset_varnames: dict,
    output_folder: str | Path,
    boundary_number_conversion: dict,
    run_initial_condition: bool = True,
    run_boundary_conditions: bool = True,
    vgrid_path: str | Path = None,
    preview: bool = False,
):
    """
    Find the required files, set up the necessary data, and regrid the dataset.

    Parameters
    ----------
    folder : str or Path
        Path to the folder containing the dataset files.
    input_dataset_regex : str
        Regular expression pattern to match dataset files.
    date_format : str
        Date format string used to parse dates in filenames (e.g., "%Y%m%d").
    start_date : str
        Start date of the dataset range in `YYYYMMDD` format.
    end_date : str
        End date of the dataset range in `YYYYMMDD` format.
    hgrid : str or Path
        Path to the horizontal grid file used for regridding.
    dataset_varnames : dict
        Mapping of variable names in the dataset to standardized names.
        Example:
        {
            "time": "time",
            "latitude": "yh",
            "longitude": "xh",
            "depth": "zl"
        }
    output_folder : str or Path
        Path to the folder where the regridded dataset will be saved.
    boundary_number_conversion : dict
        Dictionary mapping boundary names to numerical IDs.
        Example:
        {
            "north": 1,
            "east": 2,
            "south": 3,
            "west": 4
        }
    run_initial_condition :  bool
        Whether or not to run the initial condition, defaults to true
    run_boundary_conditions :  bool
        Whether or not to run the boundary conditions, defaults to true
    vgrid_path: str or Path
        Path to the Vertical Coordinate required for the initial condition
    preview :  bool
        Whether or not to preview the run of this function, defaults to false

    Returns
    -------
    None
        The regridded dataset files are saved to the specified `output_folder`.

    """
    logger.info("Parsing Raw Data Folder")
    output_folder = Path(output_folder)
    # If run_initial_condition is True, vgrid_path must exist as well
    if run_initial_condition and not os.path.exists(vgrid_path):
        raise FileNotFoundError(
            "Vgrid file must exist if run_initial_condition is set to true"
        )

    # Create output folders if not created - temp patch until regional-mom6 creates this folders by default
    Path(output_folder).mkdir(exist_ok=True)
    (Path(output_folder) / "weights").mkdir(exist_ok=True)

    # Parse data folder and find required files
    start_date = datetime.strptime(start_date, date_format)
    end_date = datetime.strptime(end_date, date_format)
    boundary_file_list = parse_dataset_folder(folder, input_dataset_regex, date_format)
    issues = check_date_continuity(boundary_file_list)
    if issues:
        for boundary, msgs in issues.items():
            for m in msgs:
                logger.warning("[%s] %s", boundary, m)
    else:
        logger.info("All boundaries continuous and non-overlapping.")

    boundary_list = boundary_file_list.keys()

    for boundary in boundary_list:
        if boundary not in boundary_number_conversion:
            logger.error(
                f"Boundary '{boundary}' not found in the boundary_number_conversion. We need the boundary_number_conversion for all boundaries to identify what number to label each segment."
            )
            return

    matching_files = defaultdict(list)
    for boundary in boundary_list:
        for file_start, file_end, file_path in boundary_file_list[boundary]:
            if file_start <= end_date and file_end >= start_date:
                matching_files[boundary].append((file_start, file_end, file_path))

    logger.info("Setting up required information")
    # Setup required information for regridding

    # Read in hgrid
    hgrid = xr.open_dataset(hgrid_path)

    logger.info("Starting regridding")
    output_file_names = []

    # Determine fill method
    fill_method = rm6.regridding.fill_missing_data
    if "boundary_fill_method" in dataset_varnames:
        if dataset_varnames["boundary_fill_method"] == "mom6_bathy":
            raise ValueError("This is not quite supported yet")
            fill_method = m6b_fill_missing_data_wrapper
        elif dataset_varnames["boundary_fill_method"] != "regional_mom6":
            raise ValueError("Provided fill method is not supported yet. ")

    # Do Regridding (Boundaries)
    if run_boundary_conditions:
        for boundary in matching_files.keys():
            for file_start, file_end, file_path in matching_files[boundary]:
                file_path = Path(file_path)
                # Rename output file
                output_file_path = Path(
                    output_folder
                ) / "forcing_obc_segment_{:03d}.nc".format(
                    boundary_number_conversion[boundary]
                )

                # Rename file
                boundary_str = f"{boundary_number_conversion[boundary]:03d}"
                file_start_date = file_start.strftime(date_format)
                file_end_date = file_end.strftime(date_format)
                filename_with_dates = "forcing_obc_segment_{}_{}_{}.nc".format(
                    boundary_str, file_start_date, file_end_date
                )
                output_file_names.append(filename_with_dates)
                output_file_path_with_dates = Path(output_folder) / filename_with_dates
                if not preview:
                    if output_file_path_with_dates.exists():
                        logger.info(
                            f"Output file {output_file_path_with_dates} already exists. It will be skipped."
                        )
                    else:
                        # Use Segment Class
                        seg = rm6.segment(
                            hgrid=hgrid,
                            bathymetry_path=None,
                            outfolder=Path(output_folder),
                            segment_name="segment_{:03d}".format(
                                boundary_number_conversion[boundary]
                            ),
                            orientation=boundary,
                            startdate=file_start,
                            repeat_year_forcing=False,
                        )
                        kwargs = {}
                        if "calendar" in dataset_varnames:
                            kwargs["calendar"] = dataset_varnames["calendar"]
                            kwargs["time_units"] = dataset_varnames["time_units"]
                        seg.regrid_velocity_tracers(
                            infile=file_path,  # location of raw boundary
                            varnames=dataset_varnames,
                            arakawa_grid=None,  # Already organized into the correct mapping format
                            rotational_method=rm6.rotation.RotationMethod.EXPAND_GRID,
                            regridding_method="bilinear",
                            fill_method=fill_method,
                            **kwargs,  # Only passes time info if it exists
                        )

                        logger.info(f"Saving regridding file as {filename_with_dates}")
                        os.rename(output_file_path, output_file_path_with_dates)

    # Run Initial Condition
    if run_initial_condition:
        # Set up required information
        expt = rm6.experiment.create_empty()
        expt.hgrid = hgrid
        expt.mom_input_dir = Path(output_folder)
        expt.date_range = [start_date, None]
        vgrid_from_file = xr.open_dataset(vgrid_path)
        expt.vgrid = expt._make_vgrid(
            vgrid_from_file.dz.data
        )  # renames/changes meta data
        file_path = Path(folder) / "ic_unprocessed.nc"
        matching_files["IC"] = [("None", "None", file_path)]
        if not preview:
            if (expt.mom_input_dir / "init_eta.nc").exists():
                logger.info(
                    f"Initial condition files already exist. They will be skipped."
                )
            else:
                expt.setup_initial_condition(
                    file_path, dataset_varnames, arakawa_grid=None
                )
            if (expt.mom_input_dir / "init_eta_filled.nc").exists():
                logger.info(
                    f"Initial condition filled files already exist. They will be skipped."
                )
            else:
                # Add the M6b Fill method onto the initial conditions
                logger.info("Start mom6_bathy fill...")
                # Read in bathymetry
                grid = Grid.from_supergrid(hgrid_path)

                # Have to get min depth from the file first
                with xr.open_dataset(bathymetry) as ds:
                    min_depth = ds.attrs.get("min_depth")
                bathymetry = Topo.from_topo_file(
                    grid=grid, topo_file_path=bathymetry, min_depth=min_depth
                )

                # ETA - no depth
                file_path = output_folder / "init_eta.nc"
                ds = xr.open_dataset(file_path, mask_and_scale=True)
                ds["eta_t"][:] = m6b.utils.fill_missing_data(
                    ds["eta_t"].values, bathymetry.tmask.values
                )
                ds["eta_t"] = final_cleanliness_fill(ds["eta_t"], "nx", "ny")
                encoding = {
                    "eta_t": {"_FillValue": None},
                }
                ds = ds.fillna(0)
                ds.to_netcdf(output_folder / "init_eta_filled.nc", encoding=encoding)

                # Velocity
                file_path = output_folder / "init_vel.nc"
                ds = xr.open_dataset(file_path, mask_and_scale=True)
                z_act = "zl"

                for z_ind in range(ds[z_act].shape[0]):
                    ds["u"][z_ind] = m6b.utils.fill_missing_data(
                        ds["u"][z_ind].values, bathymetry.umask.values
                    )
                    ds["v"][z_ind] = m6b.utils.fill_missing_data(
                        ds["v"][z_ind].values, bathymetry.vmask.values
                    )
                ds["v"] = final_cleanliness_fill(ds["v"], "nx", "nyp", "zl")
                ds["u"] = final_cleanliness_fill(ds["u"], "nxp", "ny", "zl")
                encoding = {
                    "u": {"_FillValue": netCDF4.default_fillvals["f4"]},
                    "v": {"_FillValue": netCDF4.default_fillvals["f4"]},
                }
                ds = ds.fillna(0)
                ds.to_netcdf(output_folder / "init_vel_filled.nc", encoding=encoding)

                # Tracers
                file_path = output_folder / "init_tracers.nc"
                ds = xr.open_dataset(file_path, mask_and_scale=True)
                for var in ["temp", "salt"]:
                    z_act = "zl"
                    for z_ind in range(ds[z_act].shape[0]):
                        ds[var][z_ind] = m6b.utils.fill_missing_data(
                            ds[var][z_ind].values, bathymetry.tmask.values
                        )
                    ds[var] = final_cleanliness_fill(ds[var], "nx", "ny", "zl")
                encoding = {
                    "temp": {"_FillValue": -1e20, "missing_value": -1e20},
                    "salt": {"_FillValue": -1e20, "missing_value": -1e20},
                }

                ds = ds.fillna(0)
                ds.to_netcdf(
                    output_folder / "init_tracers_filled.nc", encoding=encoding
                )
                logger.info("...end mom6_bathy fill.")
        output_file_names.append("init_eta_filled.nc")
        output_file_names.append("init_vel_filled.nc")
        output_file_names.append("init_tracers_filled.nc")

    if not preview:
        logger.info("Finished regridding")
        return
    elif preview:
        return {
            "matching_files": matching_files,
            "output_folder": output_folder,
            "output_file_names": output_file_names,
        }


def final_cleanliness_fill(var, x_dim, y_dim, z_dim=None):
    var = (
        var.where(var != 0)  # convert 0.0 → NaN
        .interpolate_na(x_dim, method="linear")  # interpolate along x
        .ffill(x_dim)
        .bfill(x_dim)
        .ffill(y_dim)  # fill along y
        .bfill(y_dim)
    )
    if z_dim != None:
        var = var.ffill(z_dim)
    return var


def capture_fill_metadata(ds):
    """
    Return a dict mapping variable names → {'_FillValue': ..., 'missing_value': ...}
    Only stores attributes that exist.
    """
    fillmeta = {}

    for var in ds.data_vars:
        meta = {}
        attrs = ds[var].attrs

        if "_FillValue" in attrs:
            meta["_FillValue"] = attrs["_FillValue"]
        if "missing_value" in attrs:
            meta["missing_value"] = attrs["missing_value"]

        if meta:
            fillmeta[var] = meta

    return fillmeta


def m6b_fill_missing_data_wrapper(ds, xdim, zdim, fill):
    raise ValueError("This is just skeleton code and is not supported")
    if zdim is not None:
        if type(zdim) != list:
            zdim = [zdim]
            for z in zdim:
                if z in ds.dims:
                    for z_ind in range(ds.shape[1]):
                        filled = fill_missing_data(
                            ds[z_ind].values, np.ones_like(ds[z_ind].values)
                        )
        return filled
    else:
        return fill_missing_data(ds.values, np.ones_like(ds.values))


if __name__ == "__main__":
    print(
        "This is the regrid of the extract forcings workflow, don't run this directly!"
    )
