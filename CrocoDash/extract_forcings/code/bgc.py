import shutil
import xesmf as xe 
import xarray as xr 
import cftime
import numpy as np

def process_bgc_ic(file_path, output_path):
    """
    Copy BGC initial condition file 

    Parameters:
    - file_path: str, path to the original BGC IC file
    - output_path: str, path to save the processed BGC IC file

    Returns:
    - None
    """

    shutil.copy(file_path, output_path)

def process_bgc_iron_forcing(nx, ny, MARBL_FESEDFLUX_FILE, MARBL_FEVENTFLUX_FILE, inputdir):
    """
    Create dummy iron forcing files for MARBL.
    Parameters:
    - nx: int, number of grid points in x-direction
    - ny: int, number of grid points in y-direction
    - MARBL_FESEDFLUX_FILE: str, filename for sediment flux input
    - MARBL_FEVENTFLUX_FILE: str, filename for event flux input
    - inputdir: str, directory to save the generated files
    Returns:
    - None 
    """
    depth = 103
    depth_edges = depth + 1
    dz = 6000.0 / depth
    DEPTH = np.linspace(dz / 2, 6000.0 - dz / 2, depth)
    DEPTH_EDGES = np.linspace(0, 6000, depth_edges)
    ds = xr.Dataset(
        {
            "DEPTH": (["DEPTH"], DEPTH),
            "DEPTH_EDGES": (["DEPTH_EDGES"], DEPTH_EDGES),
            "FESEDFLUXIN": (
                ["DEPTH", "ny", "nx"],
                np.zeros((depth, ny, nx), dtype=np.float32),
            ),
            "KMT": (["ny", "nx"], np.zeros((ny, nx), dtype=np.int32)),
            "TAREA": (["ny", "nx"], np.zeros((ny, nx), dtype=np.float64)),
        }
    )
    # Assign attributes
    ds["DEPTH"].attrs = {"units": "m", "edges": "DEPTH_EDGES"}
    ds["DEPTH_EDGES"].attrs = {"units": "m"}
    ds["FESEDFLUXIN"].attrs = {
        "_FillValue": 1.0e20,
        "units": "micromol/m^2/d",
        "long_name": "Fe sediment flux (total)",
    }
    ds["TAREA"].attrs = {"units": "m^2"}
    # Add global attributes
    ds.attrs = {
        "history": "Created with xarray (this file is empty)",
    }
    ds.to_netcdf(inputdir / "ocnice" / MARBL_FESEDFLUX_FILE)
    ds.to_netcdf(inputdir / "ocnice" / MARBL_FEVENTFLUX_FILE)

def process_river_nutrients(global_river_nutrients_filepath, ocn_grid, ROF2OCN_LIQ_RMAPNAME, river_nutrients_nnsm_filepath):
           
            # Open Dataset & Create Regridder
            global_river_nutrients = xr.open_dataset(
                global_river_nutrients_filepath
            )
            global_river_nutrients = global_river_nutrients.assign_coords(
                lon=((global_river_nutrients.lon + 360) % 360)
            )
            global_river_nutrients = global_river_nutrients.sortby("lon")
            grid_t_points = xr.Dataset()
            grid_t_points["lon"] = ocn_grid.tlon
            grid_t_points["lat"] = ocn_grid.tlat
            glofas_grid_t_points = xr.Dataset()
            glofas_grid_t_points["lon"] = global_river_nutrients.lon
            glofas_grid_t_points["lon"].attrs["units"] = "degrees"
            glofas_grid_t_points["lat"] = global_river_nutrients.lat
            glofas_grid_t_points["lat"].attrs["units"] = "degrees"
            print("Creating regridder for river nutrients...")
            regridder = xe.Regridder(
                glofas_grid_t_points,
                grid_t_points,
                method="bilinear",
                reuse_weights=True,
                filename=ROF2OCN_LIQ_RMAPNAME,
            )

            # Open Dataset & Unit Convert

            vars = [
                "din_riv_flux",
                "dip_riv_flux",
                "don_riv_flux",
                "don_riv_flux",
                "dsi_riv_flux",
                "dsi_riv_flux",
                "dic_riv_flux",
                "alk_riv_flux",
                "doc_riv_flux",
            ]
            conversion_factor = 0.01  # nmol/cm^2/s -> mmol/m^2/s
            for v in vars:
                global_river_nutrients[v] = (
                    global_river_nutrients[v] * conversion_factor
                )
                global_river_nutrients[v].attrs["units"] = "mmol/cm^2/s"

            print("Regridding river nutrients...")
            river_nutrients_remapped = regridder(global_river_nutrients)

            # Write out
            print("Writing out river nutrients...")
            # new time value as cftime
            new_time_val = cftime.DatetimeNoLeap(1900, 1, 1, 0, 0, 0)

            # select only variables that have 'time' as a dimension
            vars_with_time = [
                v
                for v in river_nutrients_remapped.data_vars
                if "time" in river_nutrients_remapped[v].dims
            ]

            # create new slice only for these
            ref_slice_new = (
                river_nutrients_remapped[vars_with_time]
                .isel(time=0)
                .expand_dims("time")
                .copy()
            )
            ref_slice_new = ref_slice_new.assign_coords(time=[new_time_val])

            # concatenate along time
            river_nutrients_remapped_time_added = xr.concat(
                [ref_slice_new, river_nutrients_remapped[vars_with_time]], dim="time"
            )

            # assign the new time coordinate
            river_nutrients_remapped_time_added = (
                river_nutrients_remapped_time_added.assign_coords(
                    time=np.concatenate(
                        [[new_time_val], river_nutrients_remapped["time"].values]
                    )
                )
            )

            # combine back with variables that don’t have time
            vars_without_time = [
                v
                for v in river_nutrients_remapped.data_vars
                if "time" not in river_nutrients_remapped[v].dims
            ]
            for v in vars_without_time:
                river_nutrients_remapped_time_added[v] = river_nutrients_remapped[v]

            # add units to all data vars
            for var in vars:
                river_nutrients_remapped_time_added[var].attrs["units"] = "mmol/cm^2/s"
            time_units = "days since 0001-01-01 00:00:00"
            time_calendar = "noleap"
            time_num = cftime.date2num(
                river_nutrients_remapped_time_added["time"].values,
                units=time_units,
                calendar=time_calendar,
            )

            # replace time coordinate with float64 numeric values
            river_nutrients_remapped_cleaned = (
                river_nutrients_remapped_time_added.assign_coords(
                    time=("time", np.array(time_num, dtype="float64"))
                )
            )

            # Change nx,ny to lon,lat
            river_nutrients_remapped_cleaned = (
                river_nutrients_remapped_cleaned.rename_dims({"nx": "lon", "ny": "lat"})
            )

            # set CF-compliant attrs
            river_nutrients_remapped_cleaned["time"].attrs.update(
                {
                    "units": time_units,
                    "calendar": "noleap",
                    "long_name": "time",
                }
            )

            # encoding only for data vars
            encoding = {
                var: {"_FillValue": np.NaN}
                for var in river_nutrients_remapped_cleaned.data_vars
            }

            river_nutrients_remapped_cleaned.to_netcdf(
                river_nutrients_nnsm_filepath,
                encoding=encoding,
                unlimited_dims=["time"],
            )