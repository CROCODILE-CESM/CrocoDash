# Extract Forcings

The final step of the CrocoDash workflow is extracting and processing all forcing data for your simulation: initial conditions, boundary conditions, tides, biogeochemistry, and more. You trigger this from Python via `case.process_forcings()`, or from the shell via `crocodash process`.

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

# Run only initial + boundary conditions
crocodash process --caseroot ~/croc_cases/mycase --ic --bc

# Run all but skip tides and runoff
crocodash process --caseroot ~/croc_cases/mycase --all --skip tides runoff

# Ran from inside the extract_forcings/ directory — no --caseroot needed
cd ~/scratch/croc_input/mycase/extract_forcings
crocodash process --all
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
| Regridding & OBC extraction | [regional-mom6](https://github.com/COSIMA/regional-mom6) | `regrid_dataset_piecewise.py` |
| Fill & grid utilities | [mom6_forge](https://github.com/NCAR/mom6_forge) | `regrid_dataset_piecewise.py`, BGC modules |
| Data formatting | `netCDF4`, `xarray` | Throughout |

If you want to modify how regridding or initial/boundary conditions are processed, the main file to look at is `CrocoDash/extract_forcings/regrid_dataset_piecewise.py`, which calls `regional-mom6` under the hood.
