import json
import os
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta
from CrocoDash.topo import *
from CrocoDash.grid import *
from CrocoDash import logging
from CrocoDash.raw_data_access.registry import ProductRegistry

logger = logging.setup_logger(__name__)

_NETCDF_MAGIC = (b"\x89HDF", b"CDF\x01", b"CDF\x02")


class Config:

    def __init__(self, config_path: str = "config.json"):

        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self.ocn_grid = Grid.from_supergrid(self.config["basic"]["paths"]["hgrid_path"])
        topo = xr.open_dataset(
            self.config["basic"]["paths"]["bathymetry_path"], decode_times=False
        )

        # Co-locate the TopoLibrary version-control dir alongside the case's config
        # file instead of letting it default to the caller's cwd (which pollutes
        # the repository root during tests).
        topo_library_dir = Path(config_path).resolve().parent / "TopoLibrary"

        self.ocn_topo = Topo.from_topo_file(
            self.ocn_grid,
            self.config["basic"]["paths"]["bathymetry_path"],
            min_depth=topo.attrs["min_depth"],
            version_control_dir=topo_library_dir,
        )
        self.inputdir = Path(self.config["basic"]["paths"]["input_dataset_path"])

    def keys(self):
        return self.config.keys()

    def __getitem__(self, key):
        return self.config[key]


def parse_dataset_folder(
    folder: str | Path, input_dataset_regex: str, date_format: str
):
    """
    Parse a folder to find and extract dataset file information based on a regex pattern.

    Parameters
    ----------
    folder : str or Path
        Path to the folder containing the dataset files.
    input_dataset_regex : str
        Regular expression pattern to match dataset filenames.
        Example: `"(north|east|south|west)_unprocessed\\.(\\d{8})_(\\d{8})\\.nc"`
    date_format : str
        Date format string used to parse dates in filenames (e.g., "%Y%m%d").

    Returns
    -------
    dict
        Dictionary mapping boundaries to a list of tuples with:
        - Start date (`datetime`)
        - End date (`datetime`)
        - Full file path (`Path`)

        Example:
        {
            "north": [(datetime(2000, 1, 1), datetime(2000, 1, 2), Path("/path/to/north_20000101_20000102.nc"))],
            "east": [(datetime(2000, 1, 3), datetime(2000, 1, 4), Path("/path/to/east_20000103_20000104.nc"))]
        }

    """
    # Dictionary to store boundary info
    boundary_file_list = defaultdict(list)

    # Regex Pattern for the dataset
    pattern = re.compile(input_dataset_regex)

    # Iterate through the folder provided for dataset files
    for file in os.listdir(folder):

        # Get File Path
        file_path = os.path.join(folder, file)

        # Check if file matches
        match = pattern.match(file)
        if match:

            # Extract information
            boundary, start_date, end_date = match.groups()

            # Convert dates to datetime objects
            start_date = datetime.strptime(start_date, date_format)
            end_date = datetime.strptime(end_date, date_format)

            # Append (file path, start date, end date)
            boundary_file_list[boundary].append((start_date, end_date, file_path))

    # Sort the date ranges for each boundary
    for boundary in boundary_file_list:
        boundary_file_list[boundary].sort()

    return boundary_file_list


def is_valid_netcdf(path: Path) -> bool:
    """Check a file's magic bytes match a known NetCDF format (HDF5, classic, or 64-bit offset)."""
    try:
        with open(path, "rb") as f:
            header = f.read(4)
        return any(header.startswith(m) for m in _NETCDF_MAGIC)
    except OSError:
        return False


def get_data_access_function(product_name: str, function_name: str):
    """Load the product registry and return the raw access function for (product_name, function_name)."""
    ProductRegistry.load()
    return ProductRegistry.get_access_function(product_name, function_name)


def build_forcing_request(product_info: dict) -> tuple[list, dict]:
    """Build the (variables, extra_args) an access function needs from a forcing product_info dict."""
    phys_vars = [
        product_info["u_var_name"],
        product_info["v_var_name"],
        product_info["eta_var_name"],
        product_info["tracer_var_names"]["temp"],
        product_info["tracer_var_names"]["salt"],
    ]
    extra_tracers = [
        v
        for k, v in product_info["tracer_var_names"].items()
        if k not in ("temp", "salt")
    ]
    variables = phys_vars + extra_tracers
    extra_args = {
        key: product_info[key]
        for key in ("dataset_path", "date_format", "regex", "delimiter")
        if key in product_info
    }
    return variables, extra_args


def fetch_raw_chunk(
    data_access_fn,
    dates: list,
    latlon: dict,
    output_folder: str | Path,
    output_filename: str,
    variables: list,
    extra_args: dict,
) -> Path:
    """Download one raw data chunk, skipping if a valid output file already exists.

    Shared by obc.py and initial_condition.py — both fetch a chunk of raw data
    for a given date range and bounding box, and both need to be idempotent
    across re-runs.
    """
    output_file = Path(output_folder) / output_filename

    if output_file.exists():
        if not is_valid_netcdf(output_file):
            raise RuntimeError(
                f"{output_file} exists but is not valid NetCDF. Delete it and re-run."
            )
        logger.info(f"{output_file.name} already exists. Skipping.")
        return output_file

    data_access_fn(
        dates=dates,
        lat_min=latlon["lat_min"],
        lat_max=latlon["lat_max"],
        lon_min=latlon["lon_min"],
        lon_max=latlon["lon_max"],
        output_folder=output_folder,
        output_filename=output_file.name,
        variables=variables,
        **extra_args,
    )
    return output_file


def check_date_continuity(boundary_file_list: dict):
    """
    Check for overlaps or missing dates between consecutive files.
    """
    issues = defaultdict(list)

    for boundary, files in boundary_file_list.items():
        for (prev_start, prev_end, prev_file), (next_start, next_end, next_file) in zip(
            files, files[1:]
        ):
            # Expect next_start == prev_end + 1 day
            expected_next = prev_end + timedelta(days=1)
            if next_start < expected_next:
                issues[boundary].append(
                    f"Overlap: {prev_file} ({prev_start:%Y-%m-%d} → {prev_end:%Y-%m-%d}) "
                    f"and {next_file} ({next_start:%Y-%m-%d} → {next_end:%Y-%m-%d})"
                )
            elif next_start > expected_next:
                issues[boundary].append(
                    f"Gap: {prev_file} ends {prev_end:%Y-%m-%d}, "
                    f"next {next_file} starts {next_start:%Y-%m-%d}"
                )

    return issues
