"""
Data Access Module -> NESTING

Provides diag_table entries for 3D cross-section slices from a parent MOM6 run,
and loads those slices for use as OBC forcing in a nested child domain.
"""

import xarray as xr
import pandas as pd
from pathlib import Path

from CrocoDash.raw_data_access.base import *


class NESTING(ForcingProduct):
    product_name = "nesting"
    description = "MOM6 regional nesting cross-section slices for use as OBC forcing in a nested child domain run"
    link = "https://mom6.readthedocs.io/en/main/api/generated/pages/Diagnostics.html"

    time_var_name = "time"
    time_units = "days"
    boundary_fill_method = "regional_mom6"
    u_var_name = "uo"
    v_var_name = "vo"
    eta_var_name = "zos"
    depth_coord = "z_l"
    tracer_x_coord = "xh"
    tracer_y_coord = "yh"
    u_x_coord = "xq"
    u_y_coord = "yh"
    v_x_coord = "xh"
    v_y_coord = "yq"
    tracer_var_names = {"temp": "thetao", "salt": "so"}

    SLICE_VARIABLES = ["volcello", "thetao", "so", "uo", "vo", "zos"]
    BUFFER_DEG = 0.5

    @accessmethod(
        description=(
            "Load nesting slice output from a parent MOM6 run directory, "
            "or print diag_table entries if slice files are not yet present"
        ),
        type="python",
    )
    def get_nesting_slices(
        dates: list,
        variables=None,
        lon_min=None,
        lon_max=None,
        lat_min=None,
        lat_max=None,
        output_folder=Path(""),
        output_filename="nesting_slices.nc",
        input_dir=None,
        case_prefix="",
    ):
        """
        Check whether nesting slice output files exist in input_dir for each named
        cross-section in slices. If all files are found and cover the requested dates,
        load and save them to output_folder/output_filename (one NetCDF group per slice)
        and return the output path. If any slice files are missing or dates are not
        covered, print the diag_table entries needed for the parent run and return None.

        Parameters
        ----------
        dates : list
            [start_date, end_date] strings, e.g. ["2020-01-01", "2020-03-31"]
        input_dir : Path or str
            Parent MOM6/CESM run history directory to search for slice files.
        case_prefix : str
            Prefix used in diag_table file names, e.g. "carib12_credit_runoff_01.mom6"
        slices : list of dict
            Each dict: {"name": str, "lon_min": float, "lon_max": float,
                        "lat_min": float, "lat_max": float}
        """
        if variables is None:
            variables = NESTING.SLICE_VARIABLES

        output_folder = Path(output_folder)
        input_dir = Path(input_dir) if input_dir is not None else None

        # --- Step 1: Locate files for each slice ---
        found_files = {}
        missing_slices = []

        if input_dir is not None and input_dir.is_dir():
            matches = sorted(input_dir.glob(f"{case_prefix}.{name}*.nc"))
            if matches:
                found_files = matches
            else:
                missing_slices = True
        else:
            missing_slices = True

        # --- Step 2: Missing files → print diag_table config and exit ---
        if missing_slices:
            NESTING.logger.warning(
                f"Slice files not found in {input_dir}. "
                "Add the entries below to your parent run's diag_table and rerun."
            )
            diag_text = _build_diag_table_entries(
                "[nameofboundary]",
                lon_min,
                lon_max,
                lat_min,
                lat_max,
                case_prefix,
                NESTING.BUFFER_DEG,
            )
            print(
                "\n=== Add these entries to your parent run's diag_table ===\n"
                + diag_text
            )
            return None

        # --- Step 3: Date coverage check ---
        start_ts = pd.Timestamp(dates[0])
        end_ts = pd.Timestamp(dates[-1])
        coverage_ok = True

        for name, file_paths in found_files.items():
            ds = xr.open_mfdataset(
                file_paths, combine="by_coords", decode_timedelta=False
            )
            t_min = _to_timestamp(ds.time.values[0])
            t_max = _to_timestamp(ds.time.values[-1])
            if t_min > start_ts or t_max < end_ts:
                NESTING.logger.warning(
                    f"Slice '{name}' covers {t_min.date()} → {t_max.date()} "
                    f"but {start_ts.date()} → {end_ts.date()} was requested."
                )
                coverage_ok = False

        if not coverage_ok:
            NESTING.logger.warning(
                "Date coverage check failed. Check that your parent run covers the full date range."
            )
            return None

        # --- Step 4: Load, time-filter, and save per-slice groups ---
        output_path = output_folder / output_filename
        mode = "w"
        for name, file_paths in found_files.items():
            ds = xr.open_mfdataset(
                file_paths, combine="by_coords", decode_timedelta=False
            )
            ds = ds.sel(time=slice(start_ts, end_ts))
            ds.to_netcdf(output_path, mode=mode, group=name)
            mode = "a"

        NESTING.logger.info(f"Nesting slices saved to {output_path}")
        return output_path


def _build_diag_table_entries(
    name, lon_min, lon_max, lat_min, lat_max, case_prefix, buffer_deg=0.5
):
    """Return a diag_table-formatted string for a list of nesting cross-sections."""
    variables = ["volcello", "thetao", "so", "uo", "vo", "zos"]

    file_lines = []
    field_lines = []

    file_name = f"{case_prefix}.{name}%4yr-%2mo"
    region = (
        f"{lon_min - buffer_deg} {lon_max + buffer_deg} "
        f"{lat_min - buffer_deg} {lat_max + buffer_deg}  -1 -1"
    )

    file_lines.append(
        f'"{file_name}",  1,  "days",  1,  "days",  "time",  1,  "months"'
    )
    for var in variables:
        field_lines.append(
            f'"ocean_model_z", "{var}", "{var}", "{file_name}", "all", "mean", "{region}", 2'
        )

    return (
        "# --- File entries ---\n"
        + "\n".join(file_lines)
        + "\n\n# --- Field entries ---\n"
        + "\n".join(field_lines)
        + "\n"
    )


def _to_timestamp(t):
    """Convert a time value (numpy datetime64, cftime, str) to pandas Timestamp."""
    try:
        return pd.Timestamp(t)
    except Exception:
        return pd.Timestamp(str(t))
