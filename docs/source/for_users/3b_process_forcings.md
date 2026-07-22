# 3b. Process Forcings (`case.process_forcings`)

The final part of the CrocoDash workflow is extracting and processing all the forcing data your simulation needs. This includes initial conditions, boundary conditions, tidal forcings, biogeochemistry data, and more. You process all of this data through the `case.process_forcings` call. `case.process_forcings` wraps a submodule of CrocoDash called extract_forcings. Extract_forcings is a set of scripts to process each forcing, like initial/boundary conditions, tides, etc... You trigger this from Python via `case.process_forcings()`, or from the shell via `crocodash process`.

## Workflow Overview

1. `case.configure_forcings(...)` — writes `inputdir/extract_forcings/config.json` with your case-specific forcing setup
2. `case.process_forcings(...)` — reads that config and runs the extraction pipeline
3. Outputs land in `inputdir/ocnice/`

The key insight: **you don't have to run this from a Jupyter notebook**. After `configure_forcings` completes you can submit the extraction as a batch job using the CLI:

```bash
crocodash process --caseroot ~/croc_cases/mycase --all
```

## Directory Structure

```
inputdir/
├── extract_forcings/
│   └── config.json        # Written by case.configure_forcings
└── ocnice/                # Output goes here
    ├── init_eta_filled.nc
    ├── init_vel_filled.nc
    ├── init_tracers_filled.nc
    ├── forcing_obc_segment_001.nc
    └── ...
```

## Command-Line Interface

See [CLI reference](cli.md#crocodash-process) for full flag documentation.

```bash
# Run all forcing extractions
crocodash process --caseroot ~/croc_cases/mycase --all

# Run only specific forcings
crocodash process  --tides
crocodash process  --runoff
crocodash process  --bgc

# Run multiple forcings
crocodash process  --tides --runoff --bgc

# Run all except certain forcings
crocodash process  --all --skip bgcic
crocodash process  --all --skip conditions bgcic

# Skip entire processing phases
crocodash process  --all --skip conditions
```

This flexibility lets you:
- Test individual components without running everything
- Re-run one forcing type if your source data changed
- Submit to a batch queue and re-run from the CLI after a failure
- Resume a partially-completed run

## Python API

You can also call the driver directly from Python:

```python
from CrocoDash.extract_forcings.driver import run_workflow

run_workflow(
    config_path="~/scratch/croc_input/mycase/extract_forcings/config.json",
    ic=True,
    bc=True,
    tides=True,
)
```

## The Processing Pipeline

```
config.json + crocodash_state.json
    ↓
get_dataset_piecewise     (download raw OBC/IC data in time-stepped chunks)
    ↓
regrid_dataset_piecewise  (regrid to model grid, fill missing data)
    ↓
merge_piecewise_dataset   (concatenate chunks into final OBC files)
    ↓
[tides / bgc / runoff / chl modules run independently]
    ↓
inputdir/ocnice/
```

## Design Philosophy

CrocoDash delegates heavy lifting to specialist packages:

| Task | Tool | Used By |
|------|------|---------|
| Regridding & OBC extraction | [regional-mom6](https://github.com/CROCODILE-CESM/regional-mom6) | `regrid_dataset_piecewise.py` & Various Modules |
| Minor processing (fill, mapping, Chlorophyll) | [mom6_forge](https://github.com/NCAR/mom6_forge) | Various modules |
| Data formatting | `netCDF4`, `xarray` | Throughout |

If you want to modify how regridding or initial/boundary conditions are processed, the main place to look is `CrocoDash.extract_forcings.regrid_dataset_piecewise`, which calls `regional-mom6` under the hood. You can look at [regional_mom6 documentation](https://regional-mom6.readthedocs.io/en/latest/index.html) for more information, allthrough it may be difficult to tease out how we use regional_mom6 without looking into the code a bit more.

## Example: Running Forcings on Your HPC System

Here's a typical workflow for an HPC system with job queues:

1. **Set up your case locally (or on login node):**
   ```python
   case = Case(...)
   case.configure_forcings(...)  # Sets up all configuration
   ```

3. **Submit extraction as a batch job:**
   ```bash
   cd /path/to/case/input_directory/extract_forcings
   # Activate CrocoDash environment and submit to batch system!
   ```

## See also

- [3a. Configure Forcings](3a_configure_forcings.md) — the step that writes the `config.json` this driver consumes
- [Datasets](datasets.md) — the raw data sources the driver downloads from
- [Architecture](../for_developers/architecture.md) — where `extract_forcings` lives in the code and how to extend it
- [Submodule API Usage](../for_developers/submodule_api_usage.md) — exact `regional-mom6` / `mom6_forge` functions called during processing
