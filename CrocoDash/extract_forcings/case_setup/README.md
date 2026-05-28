# Case Setup

This directory contains the files needed to run the CrocoDash forcing extraction workflow for a specific case.

## Files

- **`config.json`** — Case-specific configuration (paths, dates, forcing products, component settings). Edit this before running.
- **`driver.py`** — Main workflow driver. Run from the command line or import `run_workflow` directly.
- **`driver.pbs`** — PBS batch submission script for running the workflow on HPC systems (e.g. Derecho at NCAR).

## Quickstart

### Interactive / local

```bash
# From this directory, with the CrocoDash conda environment active:
python driver.py --all                        # all components, sequential
python driver.py --bc --n-workers 4           # OBC only, 4 local dask workers
python driver.py --all --skip tides           # all except tides
python driver.py --ic --no-get                # IC, skip raw data download
```

Run `python driver.py --help` for a full list of component and cluster flags.

### PBS batch job (Derecho)

Edit `driver.pbs` to set your project/account code (`#PBS -A`) and adjust walltime/memory as needed, then submit:

```bash
qsub driver.pbs
```

For large OBC workflows that benefit from parallel processing, use the `--pbs` flag inside `driver.pbs` to spawn dask workers as separate PBS jobs:

```bash
# In driver.pbs, replace the final python line with:
python driver.py --bc --n-workers 8 --pbs --queue main --walltime 01:00:00
```

This submits 8 dask worker jobs alongside the main job, parallelising the OBC regridding step. Requires `dask-jobqueue` (included in the CrocoDash environment).
