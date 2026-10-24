# 3b. Process Forcings (`case.process_forcings`)

The final part of the CrocoDash workflow is extracting and processing all the forcing data your simulation needs. This includes initial conditions, boundary conditions, tidal forcings, biogeochemistry data, and more. You process all of this data through the `case.process_forcings` call. `case.process_forcings` wraps the `CrocoDash.forcing` package, which holds one configurator per forcing type (initial/boundary conditions, tides, BGC, runoff, chlorophyll) plus the driver that dispatches to them. You trigger this from Python via `case.process_forcings()`, or from the shell via `crocodash process`.

## Workflow Overview

1. `case.configure_forcings(...)` — writes `inputdir/extract_forcings/config.json` with your case-specific forcing setup (the directory keeps its historical name; the code lives in the installed `CrocoDash.forcing` package, not in that folder)
2. `case.process_forcings(...)` — reads that config and runs the extraction pipeline
3. Outputs land in `inputdir/ocn/`

The key insight: **you don't have to run this from a Jupyter notebook**. After `configure_forcings` completes you can submit the extraction as a batch job using the CLI:

```bash
crocodash process --caseroot ~/croc_cases/mycase --all
```

## Directory Structure

```
inputdir/
├── extract_forcings/
│   └── config.json        # Written by case.configure_forcings
└── ocn/                   # Output goes here
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
crocodash process --caseroot ~/croc_cases/mycase --tides
crocodash process --caseroot ~/croc_cases/mycase --runoff
crocodash process --caseroot ~/croc_cases/mycase --bgcic

# Run multiple forcings
crocodash process --caseroot ~/croc_cases/mycase --tides --runoff --bgcic

# Run all except certain forcings
crocodash process --caseroot ~/croc_cases/mycase --all --skip bgcic
crocodash process --caseroot ~/croc_cases/mycase --all --skip ic bgcic

# Skip both initial and boundary conditions
crocodash process --caseroot ~/croc_cases/mycase --all --skip ic bc
```

:::{note}
`--skip` matches **component flag names** (`ic`, `bc`, `tides`, `chl`, `runoff`,
`bgcic`, `bgcironforcing`, `bgcrivernutrients`), not configurator names. Passing a
configurator name such as `--skip conditions` is silently ignored — the flags it
answers to are `ic` and `bc`. There is also no bare `--bgc` flag: BGC is three
separate components.
:::

This flexibility lets you:
- Test individual components without running everything
- Re-run one forcing type if your source data changed (with `--force`, since its configuration didn't)
- Submit to a batch queue and re-run from the CLI after a failure
- Resume a partially-completed run

## Finished components are skipped

Once a component has run, `process_forcings` records it, with its configuration and
its files, in `extract_forcings/finished_steps.json`. A later run skips it (`[skip] ic`)
while its configuration is unchanged and none of its files is missing. It runs again
when `configure_forcings` changed its configuration, when one of its files is gone, or
when you force it:

```bash
crocodash process --caseroot ~/croc_cases/mycase --bc --force
```

```python
case.process_forcings(force=True)
```

Before a recorded component runs again, the files it made last time are deleted, so
they are regenerated rather than reused. `--force` keeps the downloaded and regridded
data in `extract_forcings/` and rebuilds the final files from it.

To see what a run would do without running anything, add `--preview`. It lists
each selected component as `finished` or `would run`, with the files it writes
marked `present` or `missing`:

```bash
crocodash process --caseroot ~/croc_cases/mycase --all --preview
```

```
[preview] ic: finished
    present  ocn/init_tracers_filled.nc
    present  ocn/init_eta_filled.nc
    present  ocn/init_vel_filled.nc
[preview] bc: would run
    missing  ocn/forcing_obc_segment_001.nc
    ...
```

## Large datasets

Large regional domains require large datasets. CrocoDash automatically switches to parallel downloading and regridding of Glorys data if multiple CPUs are available and a regridding step is provided in `config.json` ([see example here](https://crocodile-cesm.github.io/CrocoGallery/latest/crocodash/process-forcings/)). External infrastructure may set limits: for example, if using `get_glorys_data_from_cds_api`, Copernicus Marine Services may throw a "Too many requests" error if too many CPUs are used and they all contact the server at once. `get_glorys_data_from_rda` does not have this limitation but implies permission to access to NCAR's RDA repository. Regridding has no limitations per se.

## Python API

To process an existing case from a new Python session, read it back with
`Case.from_caseroot`. It rebuilds the case from its caseroot alone (`_crocodash_state.json`
and the `config.json` that `configure_forcings` wrote), without running `create_newcase`,
`case.setup` or visualCaseGen. `crocodash process` does the same. If the CESM tree the
case was created with has moved, pass `cesmroot=`.

```python
from CrocoDash.case import Case

case = Case.from_caseroot("/glade/u/home/<user>/croc_cases/mycase")
case.process_forcings()  # or e.g. process_bc=False to leave a component out
```

## The Processing Pipeline

```
config.json + _crocodash_state.json
    ↓
ForcingConfigRegistry.resolve_process_targets()
    ↓  {flag: (configurator, method)}
GET     — download raw OBC/IC data in time-stepped chunks   (forcing/obc.py, forcing/ic.py)
    ↓
REGRID  — regrid to the model grid, fill missing data       (forcing/mom6.py)
    ↓
MERGE   — concatenate chunks into final OBC files           (forcing/obc.py)
    ↓
[tides / bgc / runoff / chl configurators run independently]
    ↓
inputdir/ocn/
```

Each CLI flag maps onto one configurator method via that class's
`process_components` declaration:

| Flag | Configurator | Method | Module |
|---|---|---|---|
| `--ic` | `ConditionsConfigurator` | `process_ic` | `forcing/mom6.py` |
| `--bc` | `ConditionsConfigurator` | `process_bc` | `forcing/mom6.py` |
| `--tides` | `TidesConfigurator` | `process` | `forcing/tides.py` |
| `--chl` | `ChlConfigurator` | `process` | `forcing/chl.py` |
| `--runoff` | `RunoffConfigurator` | `process` | `forcing/runoff.py` |
| `--bgcic` | `BGCICConfigurator` | `process` | `forcing/bgc.py` |
| `--bgcironforcing` | `BGCIronForcingConfigurator` | `process` | `forcing/bgc.py` |
| `--bgcrivernutrients` | `BGCRiverNutrientsConfigurator` | `process` | `forcing/bgc.py` |

Adding a `process_components` entry to a new configurator surfaces its CLI flag
automatically — there is no hand-maintained flag list.

## Design Philosophy

CrocoDash delegates heavy lifting to specialist packages:

| Task | Tool | Module |
|------|------|--------|
| OBC chunking / merge | CrocoDash | `forcing/obc.py` |
| IC chunking | CrocoDash | `forcing/ic.py` |
| OBC + IC regridding | [regional-mom6](https://github.com/CROCODILE-CESM/regional-mom6) | `forcing/mom6.py` |
| IC land-fill | [mom6_forge](https://github.com/NCAR/mom6_forge) | `forcing/mom6.py` |
| Chlorophyll | [regional-mom6](https://github.com/CROCODILE-CESM/regional-mom6) | `forcing/chl.py` |
| Runoff mapping | [mom6_forge](https://github.com/NCAR/mom6_forge) | `forcing/runoff.py` |
| Data formatting | `netCDF4`, `xarray` | Throughout |

For more detail on OBC regridding, see the
[regional-mom6 documentation](https://regional-mom6.readthedocs.io/en/latest/index.html).

## See also

- [3a. Configure Forcings](3a_configure_forcings.md) — the step that writes the `config.json` this driver consumes
- [Datasets](datasets.md) — the raw data sources the driver downloads from
- [Architecture](../for_developers/architecture.md) — where `CrocoDash.forcing` lives in the code and how to extend it
- [Submodule API Usage](../for_developers/submodule_api_usage.md) — exact `regional-mom6` / `mom6_forge` functions called during processing
