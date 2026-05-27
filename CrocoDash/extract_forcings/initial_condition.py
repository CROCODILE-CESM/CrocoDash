from pathlib import Path
from datetime import datetime, timedelta
from CrocoDash import logging
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.raw_data_access.registry import ProductRegistry
import dask
import xarray as xr
import regional_mom6 as rm6
import mom6_forge as m6b
import netCDF4

logger = logging.setup_logger(__name__)


def process_initial_condition(
    product_name: str,
    function_name: str,
    product_information: dict,
    date_format: str,
    start_date: str | datetime,
    hgrid_path: str | Path,
    vgrid_path: str | Path,
    dataset_varnames: dict,
    raw_data_dir: str | Path,
    output_data_dir: str | Path,
    bathymetry_path: str | Path,
    preview: bool = False,
):
    """
    Process the initial condition (t=0) through the data retrieval pipeline.

    Args:
        product_name: The name of the data product to retrieve.
        function_name: The function to call for retrieving data.
        product_information: Variable name mappings and metadata for the forcing product.
        date_format: The date format string (e.g., "%Y%m%d").
        start_date: The start date (string or datetime).
        hgrid_path: Path to the hgrid supergrid file.
        vgrid_path: Path to the vertical grid file.
        dataset_varnames: Variable name mappings passed to rm6 regridding.
        raw_data_dir: Directory for raw downloaded data.
        output_data_dir: Directory for final MOM6-ready output files.
        bathymetry_path: Path to the bathymetry file.
        preview: Return metadata dict without executing, default False.
    """
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, date_format)

    ProductRegistry.load()
    ProductRegistry.validate_function(product_name, function_name)
    data_access_function = ProductRegistry.get_access_function(
        product_name, function_name
    )

    # Get lat,lon information for each boundary
    hgrid = xr.open_dataset(hgrid_path)
    boundary_info = Grid.get_bounding_boxes_of_rectangular_grid(hgrid)
    latlon_info = boundary_info["ic"]
    output_file = "ic_unprocessed.nc"
    end_ic_date = start_date + timedelta(days=1)
    end_ic_date_str = end_ic_date.strftime(date_format)
    start_date_str = start_date.strftime(date_format)

    # Build requested variables
    phys_vars = [
        product_information["u_var_name"],
        product_information["v_var_name"],
        product_information["eta_var_name"],
        product_information["tracer_var_names"]["temp"],
        product_information["tracer_var_names"]["salt"],
    ]
    extra_tracers = [
        v
        for k, v in product_information["tracer_var_names"].items()
        if k not in ("temp", "salt")
    ]
    extra_args = {
        key: product_information[key]
        for key in ["dataset_path", "date_format", "regex", "delimiter"]
        if key in product_information
    }
    if not preview:
        _download_initial_condition(
            data_access_function=data_access_function,
            latlon_info=latlon_info,
            raw_data_dir=raw_data_dir,
            start_date_str=start_date_str,
            end_date_str=end_ic_date_str,
            variables=phys_vars + extra_tracers,
            extra_args=extra_args,
        )

    # Set up required information
    expt = rm6.experiment.create_empty()
    expt.hgrid = hgrid
    expt.mom_input_dir = Path(output_data_dir)
    expt.date_range = [start_date, None]
    vgrid_from_file = xr.open_dataset(vgrid_path)
    expt.vgrid = expt._make_vgrid(vgrid_from_file.dz.data)  # renames/changes meta data
    file_path = Path(raw_data_dir) / "ic_unprocessed.nc"
    if not preview:
        if (expt.mom_input_dir / "init_eta.nc").exists():
            logger.info(f"Initial condition files already exist. They will be skipped.")
        else:
            expt.setup_initial_condition(file_path, dataset_varnames, arakawa_grid=None)
        if (expt.mom_input_dir / "init_eta_filled.nc").exists():
            logger.info(
                f"Initial condition filled files already exist. They will be skipped."
            )
        else:
            # Add the M6b Fill method onto the initial conditions
            logger.info("Start mom6_forge fill...")
            # Read in bathymetry
            grid = Grid.from_supergrid(hgrid_path)

            # Have to get min depth from the file first
            with xr.open_dataset(bathymetry_path) as ds:
                min_depth = ds.attrs.get("min_depth")
            bathymetry = Topo.from_topo_file(
                grid=grid, topo_file_path=bathymetry_path, min_depth=min_depth
            )

            # ETA - no depth
            file_path = Path(output_data_dir) / "init_eta.nc"
            ds = xr.open_dataset(file_path, mask_and_scale=True)
            ds["eta_t"][:] = m6b.utils.fill_missing_data(
                ds["eta_t"].values, bathymetry.tmask.values
            )
            ds["eta_t"] = final_cleanliness_fill(ds["eta_t"], "nx", "ny")
            encoding = {
                "eta_t": {"_FillValue": None},
            }
            ds = ds.fillna(0)
            ds.to_netcdf(
                Path(output_data_dir) / "init_eta_filled.nc", encoding=encoding
            )

            # Velocity
            file_path = Path(output_data_dir) / "init_vel.nc"
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
            ds.to_netcdf(
                Path(output_data_dir) / "init_vel_filled.nc", encoding=encoding
            )

            # Tracers
            file_path = Path(output_data_dir) / "init_tracers.nc"
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
                Path(output_data_dir) / "init_tracers_filled.nc", encoding=encoding
            )
            logger.info("...end mom6_forge fill.")

    if not preview:
        logger.info(
            f"Successfully retrieved {product_name} initial condition data located in {output_data_dir} directory."
        )
    if preview:
        return {
            "date": start_date_str,
            "output_file_names": output_file,
            "output_folder": output_data_dir,
        }


def _download_initial_condition(
    data_access_function,
    latlon_info: dict,
    raw_data_dir: str | Path,
    start_date_str: str,
    end_date_str: str,
    variables: list[str],
    extra_args: dict,
):
    output_file = "ic_unprocessed.nc"
    raw_data_dir = Path(raw_data_dir)
    if (raw_data_dir / output_file).exists():
        logger.info(
            f"Initial condition file {output_file} already exists. Skipping download."
        )
        return

    with dask.config.set(scheduler="synchronous"):
        data_access_function(
            dates=[start_date_str, end_date_str],
            lat_min=latlon_info["lat_min"],
            lat_max=latlon_info["lat_max"],
            lon_min=latlon_info["lon_min"],
            lon_max=latlon_info["lon_max"],
            output_folder=raw_data_dir,
            output_filename=output_file,
            variables=variables,
            **extra_args,
        )


def final_cleanliness_fill(var, x_dim, y_dim, z_dim=None):
    var = (
        var.where(var != 0)  # convert 0.0 → NaN
        .interpolate_na(x_dim, method="linear")  # interpolate along x
        .ffill(x_dim)
        .bfill(x_dim)
        .ffill(y_dim)  # fill along y
        .bfill(y_dim)
    )
    if z_dim is not None:
        var = var.ffill(z_dim)
    return var
