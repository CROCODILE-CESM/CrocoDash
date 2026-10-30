"""IC (Initial Condition) forcing extraction engine for CrocoDash.

Model-agnostic: this module gets the raw t=0 snapshot, but knows nothing
about how to regrid it. Callers (``mom6.py``, ``cice.py``, ``ww3.py``)
supply a ``regrid_fn`` that turns the raw snapshot into that target's own
initial-condition file(s) -- the GET step is shared.
"""

from pathlib import Path
from CrocoDash import logging
from CrocoDash.grid import Grid
from CrocoDash.forcing import utils
from CrocoDash.raw_data_access.region import Region
from CrocoDash.raw_data_access.time_request import TimeRequest
import dask
import xarray as xr

logger = logging.setup_logger(__name__)


def process_initial_condition(
    product_name: str,
    function_name: str,
    variables: list,
    extra_args: dict,
    dataset_varnames: dict,
    when: TimeRequest,
    hgrid_path: str | Path,
    raw_data_dir: str | Path,
    output_data_dir: str | Path,
    regrid_fn,
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
        when: The IC request: whole days ending on the run's start
            (``when.end``), reaching back far enough that coarse (e.g.
            monthly) data still holds the record at or before it. Never
            thinned.
        hgrid_path: Path to the hgrid supergrid file.
        raw_data_dir: Directory for raw downloaded data.
        output_data_dir: Directory for final output files.
        regrid_fn: Target-specific regrid step, called as
            ``regrid_fn(raw_file, hgrid, when, output_dir, dataset_varnames)``
            once the raw snapshot has been downloaded. It takes the record
            at or before the start from raw_file, which can hold more than
            one, and owns its own idempotency (this engine has no per-chunk
            state to check -- IC is a single snapshot, not a date-chunked
            series).
    """
    # obc.py creates these itself, but the driver can run IC before BC (or
    # without it), so IC cannot rely on that having happened. netCDF4 reports a
    # missing parent directory as a bare EACCES, so skipping this surfaces as a
    # misleading PermissionError rather than "no such directory".
    Path(raw_data_dir).mkdir(parents=True, exist_ok=True)
    Path(output_data_dir).mkdir(parents=True, exist_ok=True)

    data_access_function = utils.get_data_access_function(product_name, function_name)

    if getattr(data_access_function, "_how_to_use", None):
        logger.info(
            f"[{product_name}.{function_name}] Usage: {data_access_function._how_to_use}"
        )

    # The IC snapshot's box: the whole domain
    hgrid = xr.open_dataset(hgrid_path)
    box = Grid.get_bounding_boxes(hgrid)["ic"]

    _download_initial_condition(
        data_access_function=data_access_function,
        region=Region(box["lat_min"], box["lat_max"], box["lon_min"], box["lon_max"]),
        raw_data_dir=raw_data_dir,
        when=when,
        variables=variables,
        extra_args=extra_args,
    )

    raw_file = Path(raw_data_dir) / "ic_unprocessed.nc"
    regrid_fn(
        raw_file=raw_file,
        hgrid=hgrid,
        when=when,
        output_dir=Path(output_data_dir),
        dataset_varnames=dataset_varnames,
    )

    logger.info(
        f"Successfully retrieved {product_name} initial condition data located in {output_data_dir} directory."
    )


def _download_initial_condition(
    data_access_function,
    region: Region,
    raw_data_dir: str | Path,
    when: TimeRequest,
    variables: list[str],
    extra_args: dict,
):
    with dask.config.set(scheduler="synchronous"):
        utils.fetch_raw_chunk(
            data_access_fn=data_access_function,
            when=when,
            region=region,
            output_folder=raw_data_dir,
            output_filename="ic_unprocessed.nc",
            variables=variables,
            name="ic",
            extra_args=extra_args,
        )
