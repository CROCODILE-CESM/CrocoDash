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

## Large datasets

Large regional domains require large datasets. CrocoDash automatically switches to parallel downloading and regridding of Glorys data if multiple CPUs are available and a regridding step is provided in `config.json` ([see example here](https://crocodile-cesm.github.io/CrocoGallery/latest/crocodash/process-forcings/)). External infrastructure may set limits: for example, if using `get_glorys_data_from_cds_api` or `get_glorys_data_script_for_cli`, Copernicus Marine Services may throw a "Too many requests" error if too many CPUs are used and they all contact the server at once. `get_glorys_data_from_rda` does not have this limitation but implies permission to access to NCAR's RDA repository. Regridding has no limitations per se.

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
config.json + _crocodash_state.json
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

| Task | Tool | Module |
|------|------|--------|
| OBC regridding | [regional-mom6](https://github.com/COSIMA/regional-mom6) | `obc.py` |
| Initial condition regridding | [regional-mom6](https://github.com/COSIMA/regional-mom6) | `initial_condition.py` |
| IC land-fill | [mom6_forge](https://github.com/NCAR/mom6_forge) | `initial_condition.py` |
| Chlorophyll, fill, mapping | [mom6_forge](https://github.com/NCAR/mom6_forge) | Various modules |
| Data formatting | `netCDF4`, `xarray` | Throughout |

For more detail on OBC regridding, see the
[regional-mom6 documentation](https://regional-mom6.readthedocs.io/en/latest/index.html).

## See also

- [3a. Configure Forcings](3a_configure_forcings.md) — the step that writes the `config.json` this driver consumes
- [Datasets](datasets.md) — the raw data sources the driver downloads from
- [Architecture](../for_developers/architecture.md) — where `extract_forcings` lives in the code and how to extend it
- [Submodule API Usage](../for_developers/submodule_api_usage.md) — exact `regional-mom6` / `mom6_forge` functions called during processing
