"""IC (Initial Condition) forcing extraction engine for CrocoDash.

Model-agnostic: this module gets the raw t=0 snapshot, but knows nothing
about how to regrid it. Callers (``mom6.py``, ``cice.py``, ``ww3.py``)
supply a ``regrid_fn`` that turns the raw snapshot into that target's own
initial-condition file(s) -- the GET step is shared.
"""

from pathlib import Path
from datetime import datetime, timedelta
from CrocoDash import logging
from CrocoDash.grid import Grid
from CrocoDash.forcing import utils
import dask
import xarray as xr
import pandas as pd

logger = logging.setup_logger(__name__)


def process_initial_condition(
    product_name: str,
    function_name: str,
    variables: list,
    extra_args: dict,
    dataset_varnames: dict,
    start_date: str | datetime,
    hgrid_path: str | Path,
    raw_data_dir: str | Path,
    output_data_dir: str | Path,
    regrid_fn,
    preview: bool = False,
):
    """
    Process the initial condition (t=0) through the GET → REGRID pipeline.

    Args:
        product_name: The name of the data product to retrieve.
        function_name: The function to call for retrieving data.
        variables: Variable names to request from the download function
            (already resolved by the caller from its own product metadata).
        extra_args: Extra kwargs for the download function (already resolved
            by the caller).
        dataset_varnames: Opaque metadata dict forwarded to ``regrid_fn`` --
            this module never reads its keys itself.
        start_date: The start date (any pandas-parseable string or datetime).
        hgrid_path: Path to the hgrid supergrid file.
        raw_data_dir: Directory for raw downloaded data.
        output_data_dir: Directory for final output files.
        regrid_fn: Target-specific regrid step, called as
            ``regrid_fn(raw_file, hgrid, start_date, output_dir, dataset_varnames)``
            once the raw snapshot has been downloaded. Owns its own
            idempotency (this engine has no per-chunk state to check --
            IC is a single snapshot, not a date-chunked series).
        preview: Return metadata dict without executing, default False.
    """
    if not isinstance(start_date, datetime):
        start_date = pd.to_datetime(start_date).to_pydatetime()

    output_file = "ic_unprocessed.nc"
    end_ic_date = start_date + timedelta(days=1)
    end_ic_date_str = end_ic_date.strftime("%Y-%m-%d")
    start_date_str = start_date.strftime("%Y-%m-%d")

    if preview:
        return {
            "date": start_date_str,
            "output_file_names": output_file,
            "output_folder": output_data_dir,
        }

    data_access_function = utils.get_data_access_function(product_name, function_name)

    # Get lat,lon information for the IC snapshot
    hgrid = xr.open_dataset(hgrid_path)
    latlon_info = Grid.get_bounding_boxes(hgrid)["ic"]

    _download_initial_condition(
        data_access_function=data_access_function,
        latlon_info=latlon_info,
        raw_data_dir=raw_data_dir,
        start_date_str=start_date_str,
        end_date_str=end_ic_date_str,
        variables=variables,
        extra_args=extra_args,
    )

    raw_file = Path(raw_data_dir) / "ic_unprocessed.nc"
    regrid_fn(
        raw_file=raw_file,
        hgrid=hgrid,
        start_date=start_date,
        output_dir=Path(output_data_dir),
        dataset_varnames=dataset_varnames,
    )

    logger.info(
        f"Successfully retrieved {product_name} initial condition data located in {output_data_dir} directory."
    )


def _download_initial_condition(
    data_access_function,
    latlon_info: dict,
    raw_data_dir: str | Path,
    start_date_str: str,
    end_date_str: str,
    variables: list[str],
    extra_args: dict,
):
    with dask.config.set(scheduler="synchronous"):
        utils.fetch_raw_chunk(
            data_access_fn=data_access_function,
            dates=[start_date_str, end_date_str],
            latlon=latlon_info,
            output_folder=raw_data_dir,
            output_filename="ic_unprocessed.nc",
            variables=variables,
            name="ic",
            extra_args=extra_args,
        )
