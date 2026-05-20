from dask.distributed import Client

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
    "slurm": {
        "cores": 1,
        "processes": 1,
        "memory": "4GiB",
        "walltime": "01:00:00",
        "job_name": "crocodash",
    },
    "lsf": {
        "cores": 1,
        "memory": "4GiB",
        "walltime": "01:00:00",
        "job_name": "crocodash",
    },
    "sge": {
        "cores": 1,
        "memory": "4GiB",
        "job_name": "crocodash",
        # no walltime default — SGE sites vary widely on whether it's required
    },
}


def make_client(
    scheduler=None,
    n_workers=1,
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
        scheduler:     None (local), 'pbs', 'slurm', 'lsf', 'sge'
        n_workers:     Number of workers to scale to
        cores:         Cores per worker
        processes:     Processes per worker
        memory:        Memory per worker (e.g. '4GiB')
        walltime:      Walltime per worker job (e.g. '01:00:00')
        job_name:      Job name in the scheduler
        queue:         Queue/partition to submit to (site-specific, optional)
        resource_spec: PBS resource_spec string (PBS only, optional)
    """
    if scheduler is None:
        from dask.distributed import LocalCluster

        print("No scheduler specified — using LocalCluster")
        return Client(LocalCluster())

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
