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


# Defaults that are safe to assume for most HPC setups
SCHEDULER_DEFAULTS = {
    "pbs": {
        "cores": 1,
        "processes": 1,
        "memory": "4GiB",
        "walltime": "01:00:00",
        "job_name": "crocodash",
        # resource_spec intentionally omitted — too site-specific
        # queue intentionally omitted — sites vary too much
    },
    "slurm": "Isn't Tested",
}


def make_client(
    scheduler=None,
    n_workers=1,
    threads_per_worker=1,
    cores=1,
    processes=1,
    memory="4GiB",
    walltime="01:00:00",
    job_name="crocodash",
    queue=None,
    resource_spec=None,
):
    """
    Build a Dask client for the current environment.

    Args:
        scheduler:          None (local), 'pbs', 'slurm', 'lsf', 'sge'
        n_workers:          Number of workers to scale to
        threads_per_worker: Threads per local worker. Keep at 1 — xESMF/ESMF is
                            not thread-safe and will fail if multiple tasks share
                            a process. Parallelism should come from n_workers instead.
        cores:              Cores per worker (HPC schedulers only)
        processes:          Processes per worker (HPC schedulers only)
        memory:             Memory per worker (e.g. '4GiB')
        walltime:           Walltime per worker job (e.g. '01:00:00')
        job_name:           Job name in the scheduler
        queue:              Queue/partition to submit to (site-specific, optional)
        resource_spec:      PBS resource_spec string (PBS only, optional)
    """
    if scheduler is None:
        print("No scheduler specified — using LocalCluster")
        return Client(
            LocalCluster(n_workers=n_workers, threads_per_worker=threads_per_worker)
        )

    cluster_map = {
        "pbs": ("dask_jobqueue", "PBSCluster"),
        "slurm": ("dask_jobqueue", "SLURMCluster"),
        "lsf": ("dask_jobqueue", "LSFCluster"),
        "sge": ("dask_jobqueue", "SGECluster"),
    }

    scheduler = scheduler.lower()
    if scheduler not in cluster_map:
        raise ValueError(
            f"Unknown scheduler '{scheduler}'. Choose from: {list(cluster_map)}"
        )

    worker_kwargs = dict(
        cores=cores,
        processes=processes,
        memory=memory,
        walltime=walltime,
        job_name=job_name,
    )

    # Only pass optional site-specific args if provided
    if queue is not None:
        worker_kwargs["queue"] = queue
    if resource_spec is not None and scheduler == "pbs":
        worker_kwargs["resource_spec"] = resource_spec

    module, cls = cluster_map[scheduler]
    ClusterClass = getattr(__import__(module, fromlist=[cls]), cls)

    cluster = ClusterClass(**worker_kwargs)
    print(cluster.job_script())
    cluster.scale(n_workers)

    return Client(cluster)
