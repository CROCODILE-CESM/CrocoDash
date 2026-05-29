import json
import os
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta
from CrocoDash.topo import *
from CrocoDash.grid import *
from dask.distributed import Client
from dask.distributed import LocalCluster


class Config:

    def __init__(self, config_path: str = "config.json"):

        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self.ocn_grid = Grid.from_supergrid(self.config["basic"]["paths"]["hgrid_path"])
        topo = xr.open_dataset(
            self.config["basic"]["paths"]["bathymetry_path"], decode_times=False
        )

        self.ocn_topo = Topo.from_topo_file(
            self.ocn_grid,
            self.config["basic"]["paths"]["bathymetry_path"],
            min_depth=topo.attrs["min_depth"],
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


def make_local_cluster(n_workers=1, threads_per_worker=1):
    """
    Create a Dask Client backed by a LocalCluster.

    Workers are used for the GET (download) step only. REGRID and MERGE always
    run sequentially in the main process — ESMF's VM fails to initialize in
    subprocess workers on PBS/HPC systems (``ESMCI::VM::getCurrent()`` rc=545).

    For HPC batch jobs, see :func:`make_pbs_cluster`.

    Typical usage::

        from CrocoDash.extract_forcings.utils import make_local_cluster
        client = make_local_cluster(n_workers=4)
        process_obc_conditions(..., client=client)
        client.close()

    Args:
        n_workers:          Number of worker processes (used for GET/MERGE).
        threads_per_worker: Threads per worker.

    Returns:
        dask.distributed.Client connected to the LocalCluster.
    """
    return Client(
        LocalCluster(n_workers=n_workers, threads_per_worker=threads_per_worker)
    )


def make_pbs_cluster(
    n_workers,
    cores=1,
    processes=1,
    memory="4GiB",
    walltime="01:00:00",
    job_name="crocodash",
    queue=None,
    resource_spec=None,
):
    """
    Create a Dask Client backed by a PBS cluster via dask-jobqueue.

    Each Dask worker is submitted as a separate PBS job. The function prints
    the generated job script so you can verify the PBS directives before jobs
    are queued.

    Requires ``dask-jobqueue`` (``pip install dask-jobqueue``).

    Typical usage::

        from CrocoDash.extract_forcings.utils import make_pbs_cluster
        from CrocoDash.extract_forcings.case_setup.driver import run_workflow

        client = make_pbs_cluster(n_workers=8, queue="regular", walltime="02:00:00")
        run_workflow(bc=True, client=client)
        client.close()

    Args:
        n_workers:     Number of PBS jobs (workers) to submit.
        cores:         CPU cores per PBS job.
        processes:     Dask processes per PBS job (usually 1).
        memory:        Memory per PBS job (e.g. ``'4GiB'``).
        walltime:      Walltime per PBS job (e.g. ``'01:00:00'``).
        job_name:      Job name visible in ``qstat``.
        queue:         PBS queue/partition. Site-specific; omit to use the
                       scheduler default.
        resource_spec: Raw PBS ``-l`` resource string (e.g.
                       ``'select=1:ncpus=4:mem=4gb'``). Optional; overrides
                       cores/memory when set.

    Returns:
        dask.distributed.Client connected to the PBSCluster.
    """
    from dask_jobqueue import PBSCluster

    worker_kwargs = dict(
        cores=cores,
        processes=processes,
        memory=memory,
        walltime=walltime,
        job_name=job_name,
    )
    if queue is not None:
        worker_kwargs["queue"] = queue
    if resource_spec is not None:
        worker_kwargs["resource_spec"] = resource_spec

    cluster = PBSCluster(**worker_kwargs)
    print(cluster.job_script())
    cluster.scale(n_workers)
    return Client(cluster)
