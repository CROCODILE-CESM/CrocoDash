# Architecture

This page explains how CrocoDash is wired together so you can understand,
modify, or extend it. For the day-to-day user workflow see the
[user guide](../for_users/index.md).

## The four-step workflow maps onto four modules

| Workflow step | CrocoDash module(s) | Primary external dependency |
|---|---|---|
| 1. Grids (hgrid / topo / vgrid) | `grid`, `topo`, `vgrid`, `topo_editor` | [mom6_forge](https://github.com/NCAR/mom6_forge) |
| 2. Case setup | `case` | [VisualCaseGen](https://github.com/ESMCI/VisualCaseGen) + CESM CIME |
| 3a. Configure forcings | `forcing_configurations` | (internal) |
| 3b. Process forcings | `extract_forcings` | [regional-mom6](https://github.com/COSIMA/regional-mom6), `mom6_forge` |

Supporting modules you'll touch when extending CrocoDash:

- **`raw_data_access`** — unified registry-based interface to data sources
  (GLORYS, TPXO, GEBCO, GLOFAS, …).
- **`logging`** — consistent logging setup used across the package.

## Key design patterns

### Two registries

Two pieces of CrocoDash are **registry-based** so users and contributors can
extend them without touching core code:

- **`ForcingConfigRegistry`** (`forcing_configurations`) — each forcing
  configuration (Tides, BGC, Rivers, …) is a `BaseConfigurator` subclass that
  auto-registers via the `@register` decorator. The registry knows which
  configurators are required, valid, or forbidden for a given compset.
- **`ProductRegistry`** (`raw_data_access`) — each data source is a
  `ForcingProduct` subclass whose `@accessmethod` functions are discovered and
  validated at import time.

See the "Add a new …" guides for the mechanics:

- [Adding a forcing configuration](adding_forcing_configurations.md)
- [Adding a data source](adding_data_access.md)

### Configure vs. process: why they're separate

Step 3a (`case.configure_forcings`) and 3b (`case.process_forcings`) are
decoupled on purpose. Configuration is lightweight — it validates arguments,
applies `xmlchange`/`user_nl_*` edits, and writes a JSON manifest. Processing
downloads large datasets, regrids, and writes netCDF. In practice these happen
on different machines (or at least different wall-clock budgets).

The extraction system is also **fully standalone**: after `configure_forcings`,
a self-contained copy of `extract_forcings/` is placed under the case's
`inputdir/`. A user can submit `python driver.py --all` from that directory
without touching CrocoDash again. This makes HPC submission straightforward.

### Re-exports from mom6_forge

CrocoDash deliberately re-exports mom6_forge's `Grid`, `Topo`, `VGrid`,
`GridCreator`, `TopoEditor`, `VGridCreator` with no modification:

```python
# CrocoDash/grid.py
from mom6_forge.grid import *
```

The only "wrapper" work happens when CrocoDash needs a mom6_forge object in a
CESM context (grid file naming, case registration). Everything else routes
straight through.

### Validation lives in `configure_forcings`

Forcing compatibility rules live with the configurators, not scattered through
the workflow. Examples enforced there:

- Chlorophyll cannot be provided if BGC is not in the compset
- River nutrients cannot be implemented without runoff and BGC in the compset
- BGC configurators require `%MARBL` in the compset longname

When you add a new configurator, declare its compatibility via
`required_for_compsets`, `allowed_compsets`, and `forbidden_compsets` — don't
write ad-hoc `if/else` in `case.py`.

## Data flow

```text
Case(grid, topo, vgrid, compset, ...)
          │
          ▼
  _configure_case (VisualCaseGen / CIME)
          │
          ▼
  _create_grid_input_files    ──►  inputdir/ocn grid files
          │
          ▼
  _create_newcase             ──►  caseroot/ CESM case
          │
          ▼
  configure_forcings(...)
          │
          ▼
  ForcingConfigRegistry        ──►  xmlchange + user_nl_* edits
                               ──►  inputdir/extract_forcings/config.json
          │
          ▼
  process_forcings(...)
          │
          ▼
  extract_forcings/driver.py
     ├─► get_dataset_piecewise      (raw_data_access)
     ├─► regrid_dataset_piecewise   (regional-mom6 segments)
     ├─► merge_piecewise_dataset
     ├─► bgc / runoff / tides / chl (mom6_forge helpers)
          │
          ▼
                               ──►  inputdir/ocnice/... forcing files
```

## Where to add what

| You want to… | Edit… |
|---|---|
| Add a new CESM-compatible forcing (e.g. salt restoring) | new file in `forcing_configurations/`, inherits `BaseConfigurator`, decorated with `@register` |
| Add a new raw data source | new file in `raw_data_access/datasets/`, inherits `ForcingProduct`, decorated with `@accessmethod` |
| Change the regridding of OBCs | `extract_forcings/regrid_dataset_piecewise.py` (it's where we call `rm6.segment.regrid_velocity_tracers`) |
| Change bathymetry fill behaviour | `extract_forcings/regrid_dataset_piecewise.py::final_cleanliness_fill` (and look at `m6b.utils.fill_missing_data`) |
| Add a new `xmlchange` or `user_nl_*` edit | the relevant configurator's `output_params` + `configure` method |
| Change the CLI flags of `extract_forcings` | `extract_forcings/case_setup/driver.py::parse_args` / `resolve_components` |

## What CrocoDash does NOT do itself

CrocoDash is an **orchestrator**, not a reimplementation. The heavy lifting
lives in three submodules:

| Task | Tool |
|---|---|
| Regridding + OBC extraction | [regional-mom6](https://github.com/COSIMA/regional-mom6) |
| Grid / bathymetry / vgrid generation, `TopoEditor` | [mom6_forge](https://github.com/NCAR/mom6_forge) |
| CESM case creation + GUI | [VisualCaseGen](https://github.com/ESMCI/VisualCaseGen) |

For the exact function-by-function call list, see
[Submodule API Usage](submodule_api_usage.md).

## Testing

CrocoDash uses `pytest`. Run from the repo root:

```bash
# Full suite (mocked / fast)
pytest --ignore=CrocoDash/visualCaseGen -m "not workflow"

# Workflow tests (slower, may hit real data)
pytest -m "workflow"

# With coverage report
pytest --ignore=CrocoDash/visualCaseGen -m "not workflow" \
  --cov=CrocoDash --cov-report=xml --cov-branch
```

Other useful flags:

| Flag | Purpose |
|---|---|
| `-v` | verbose per-test names |
| `-x` | stop on first failure |
| `-s` | don't swallow `print()` |
| `-k EXPR` | only run tests whose name matches `EXPR` |

When developing `extract_forcings`:

- Use small date ranges and small domains
- Prefer `preview=True` in the config to dry-run
- Use the `--skip` CLI flag on `driver.py` to iterate on one component

When developing `raw_data_access`:

- New dataset classes must inherit from `ForcingProduct` and declare all
  `required_metadata` / `required_args`.
- Validation runs at import time — if metadata is missing, your tests will
  fail on import, which is the intended behaviour.

## Common workflows

### Adding a new feature

1. `git checkout -b feature/my-feature`
2. Make your code changes with proper docstrings and type hints
3. Add tests
4. Run `pytest` locally
5. `cd docs && make html` to confirm docs build
6. Open a PR

### Fixing a bug

1. Find or file the issue
2. `git checkout -b fix/issue-description`
3. Write a test that reproduces the bug
4. Fix until the test passes
5. Open a PR referencing the issue

## See also

- [Adding a forcing configuration](adding_forcing_configurations.md)
- [Adding a data source](adding_data_access.md)
- [Submodule API usage](submodule_api_usage.md) — one-stop reference for every
  upstream function CrocoDash calls.
