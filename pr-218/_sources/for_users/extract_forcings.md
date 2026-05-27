# Extract Forcings (case.process_forcings)

The final part of the CrocoDash workflow is extracting and processing all the forcing data your simulation needs. This includes initial conditions, boundary conditions, tidal forcings, biogeochemistry data, and more. You process all of this data through the `case.process_forcings` call. `case.process_forcings` wraps a submodule of CrocoDash called extract_forcings. Extract_forcings is a set of scripts to process each forcing, like initial/boundary conditions, tides, etc... extract_forcings also holds a subdirectory called case_setup. This has a driver and config file. This holds all of the specific case information to run the processing scripts. When you run the workflow, this case_setup folder gets copied into your input directory. `case.process_forcings` goes into this subfolder and runs the driver. You can also run the driver yourself through the command-line.

## Workflow Overview

When you run the CrocoDash workflow, configure_forcings and process_forcings:
1. copies a ready-to-run forcing extraction system into your case directories (from `case.configure_forcings`)
2. Runs it to download data from external sources
3. Regrids data to your custom domain
4. Formats everything for MOM6

The key insight: **you don't have to run this from a Jupyter notebook**. You get a complete, standalone extraction system that you can submit to your supercomputer's job queue.

## Directory Structure

When CrocoDash sets up your case, it creates an `extract_forcings` directory in your input folder:

```
input_directory/
├── extract_forcings/
│   ├── driver.py              # Main script that orchestrates everything
│   ├── config.json            # Your case-specific configuration
└── ocnice/                    # Output goes here
    ├── initial_conditions.nc
    ├── boundary_conditions/
    ├── tides/
    └── ...
```


## Command-Line Options

The driver script accepts several options for fine-grained control:

```bash
# Run all forcing extractions
python driver.py --all

# Run only specific forcings
python driver.py --tides
python driver.py --runoff
python driver.py --bc        # boundary conditions (OBC)
python driver.py --ic        # initial conditions

# Run multiple forcings
python driver.py --tides --runoff --bgcic

# Run all except certain forcings
python driver.py --all --skip bgcic
python driver.py --all --skip tides bgcic

# Skip raw data download (use files already on disk)
python driver.py --bc --no-get
python driver.py --ic --no-get

# Parallel OBC processing with a local cluster
python driver.py --bc --n-workers 4
```

This flexibility is intentional—you might want to:
- Test individual components without running everything
- Re-run one forcing type if your source data changed
- Run on a supercomputer queue while iterating elsewhere
- Resume after an interrupted run

## The Processing Pipeline

Here's what happens internally when the driver runs:

```
1. Load config.json with your case specifications
   ↓
2. Calls an extract_forcing script
   ↓
3. Outputs all the data to ocnice
```

## Parallelism

OBC (boundary condition) processing is parallelised internally with [Dask](https://dask.org).
By default the driver runs sequentially. There are three ways to add parallelism:

### 1. Local cluster (workstation or interactive node)

Pass `--n-workers N` on the CLI:

```bash
python driver.py --bc --n-workers 4
```

Or from Python:

```python
from CrocoDash.extract_forcings.utils import make_local_cluster
from CrocoDash.extract_forcings.case_setup.driver import run_workflow

client = make_local_cluster(n_workers=4)
run_workflow(bc=True, ic=True, client=client)
client.close()
```

### 2. PBS cluster (HPC batch system)

Create a client with `make_pbs_cluster` and pass it to `run_workflow` directly
from Python (the CLI does not support HPC schedulers — cluster config is too
site-specific for flags):

```python
from CrocoDash.extract_forcings.utils import make_pbs_cluster
from CrocoDash.extract_forcings.case_setup.driver import run_workflow

client = make_pbs_cluster(
    n_workers=8,
    queue="regular",
    walltime="02:00:00",
    memory="8GiB",
)
run_workflow(bc=True, ic=True, client=client)
client.close()
```

> **Note:** `make_pbs_cluster` requires `dask-jobqueue` (`pip install dask-jobqueue`).

### 3. Sequential (default)

Omit `--n-workers` and don't pass a client. OBC tasks run one at a time via
`dask.compute`. This is safe and requires no cluster setup — it's the right
choice for small domains or quick tests.

## Design Philosophy

CrocoDash deliberately **doesn't do all the processing itself**. Instead, it leverages packages:

| Task | Tool | Module |
|------|------|--------|
| OBC regridding | [regional-mom6](https://github.com/COSIMA/regional-mom6) | `obc.py` |
| Initial condition regridding | [regional-mom6](https://github.com/COSIMA/regional-mom6) | `initial_condition.py` |
| IC land-fill | [mom6_forge](https://github.com/NCAR/mom6_forge) | `initial_condition.py` |
| Chlorophyll, fill, mapping | [mom6_forge](https://github.com/NCAR/mom6_forge) | Various modules |
| Data formatting | `netCDF4`, `xarray` | Throughout |

For more detail on OBC regridding, see the
[regional-mom6 documentation](https://regional-mom6.readthedocs.io/en/latest/index.html).

## Example: Running Forcings on Your HPC System

Here's a typical workflow for an HPC system with PBS:

1. **Set up your case locally (or on a login node):**
   ```python
   case = Case(...)
   case.configure_forcings(...)  # writes config.json into the case input dir
   ```

2. **Run extraction — option A: submit the driver as a batch script:**
   ```bash
   cd /path/to/case/input_directory/extract_forcings
   conda activate CrocoDash
   python driver.py --all --n-workers 4
   ```

3. **Run extraction — option B: use `make_pbs_cluster` for full HPC parallelism:**
   ```python
   from CrocoDash.extract_forcings.utils import make_pbs_cluster
   from CrocoDash.extract_forcings.case_setup.driver import run_workflow

   client = make_pbs_cluster(n_workers=8, queue="regular", walltime="02:00:00")
   run_workflow(bc=True, ic=True, client=client)
   client.close()
   ```
