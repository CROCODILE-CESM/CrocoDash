# 3b. Process Forcings (`case.process_forcings`)

This is the final step of the CrocoDash workflow: actually generating all the
forcing files your simulation needs (initial conditions, boundary conditions,
tides, BGC fields, runoff mappings, chlorophyll, …).

## What this module does

`case.process_forcings` wraps the `extract_forcings` submodule. `extract_forcings`
is a collection of scripts — one per forcing type — that regrid and format data
for MOM6.

## How it integrates with `configure_forcings`

Under `extract_forcings/` there's a `case_setup/` directory containing a
`driver.py` and a `config.json`. The `config.json` is written by
[`case.configure_forcings`](3a_configure_forcings.md); it stores every path,
date, and option your case needs. The `driver.py` reads that config and
dispatches to the right processing scripts.

When you call `case.configure_forcings(...)`, CrocoDash **copies the whole
`case_setup/` directory into your case's `inputdir/extract_forcings/`**. That
copy is fully standalone: you can submit it as a batch job without going through the workflow again.

`case.process_forcings` just shells into that directory and runs the driver —
which means you can also run the driver yourself from the command line.

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
python driver.py --bgc

# Run multiple forcings
python driver.py --tides --runoff --bgc

# Run all except certain forcings
python driver.py --all --skip bgcic
python driver.py --all --skip conditions bgcic

# Skip entire processing phases
python driver.py --all --skip conditions
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

## Design Philosophy

CrocoDash deliberately **doesn't do all the processing itself**. Instead, it leverages packages:

| Task | Tool | Used By |
|------|------|---------|
| Regridding & OBC extraction | [regional-mom6](https://github.com/COSIMA/regional-mom6) | `regrid_dataset_piecewise.py` & Various Modules |
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
