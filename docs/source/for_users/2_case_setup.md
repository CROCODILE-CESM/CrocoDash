# Case Setup (`Case` object)

Once you have your grids ready, the next step is creating a `Case` object. The
`Case` is CrocoDash's main orchestration object: it wraps a CESM regional MOM6
case, ties your grid definition into CESM's machinery, and gives you the three
verbs that drive the rest of the workflow:

1. **Instantiate** `Case(...)` — sets up the case directory and registers your grid with CESM
2. **`case.configure_forcings(...)`** — declares which forcings your case needs (Step 3a)
3. **`case.process_forcings(...)`** — generates the forcing files (Step 3b)

This page covers step 2. Steps 3a and 3b have their own pages.

## Minimal example

```python
import CrocoDash as cd

case = cd.Case(
    cesmroot="/path/to/CESM",
    caseroot="/path/to/your/case",
    inputdir="/path/to/your/inputdata",
    compset="CR_JRA",
    ocn_grid=grid,
    ocn_topo=topo,
    ocn_vgrid=vgrid,
    machine="derecho",
    project="UCSG0000",
)
```

That one call:

- Initialises VisualCaseGen and the CESM CIME interface
- Validates your compset, grid, bathymetry, and vertical grid against the
  regional-MOM6 constraints
- Creates the case directory via `create_newcase`
- Writes your grid/topo/vgrid files to `inputdir`
- Applies queue/wallclock/task-count `xmlchange` settings
- Prints a summary of any **required** forcing configurations you still owe
  (these become your arguments to `configure_forcings` in step 3a)

## Required arguments

| Argument | Type | Meaning |
|---|---|---|
| `cesmroot` | path | Root of your existing CESM checkout. Must already exist. |
| `caseroot` | path | Where the CESM case directory will be created. Must NOT already exist (unless `override=True`). |
| `inputdir` | path | Where CrocoDash writes grid + forcing input files. Must NOT already exist (unless `override=True`). |
| `compset` | str | Either an alias (e.g. `"CR_JRA"`) or a full long name. See [Compsets & Inputs](compsets_and_inputs.md). |
| `ocn_grid` | `Grid` | Your horizontal grid from Step 1. |
| `ocn_topo` | `Topo` | Your bathymetry from Step 1. |
| `ocn_vgrid` | `VGrid` | Your vertical grid from Step 1. |

## Useful optional arguments

| Argument | Default | Notes |
|---|---|---|
| `machine` | auto-detected | CESM machine name. Auto-detected on known systems. |
| `project` | `None` | Project/account code. Required on machines that use accounting. |
| `atm_grid_name` | `"TL319"` | Atmosphere grid (data-atmosphere resolution). |
| `rof_grid_name` | `None` | Runoff grid. Auto-inferred from compset; required only when multiple options are available. |
| `ntasks_ocn` | VCG default | Number of MPI tasks for MOM6. |
| `job_queue` | CESM default | Batch queue. |
| `job_wallclock_time` | CESM default | Wallclock (`hh:mm:ss`). |
| `ninst` | `1` | Number of model instances (ensemble size). |
| `override` | `False` | Allow overwriting an existing `caseroot` / `inputdir`. |

## What `Case.__init__` does, in order

```text
  Case(...)
     │
     ├─► Initialize VisualCaseGen + CIME
     ├─► Resolve compset alias → longname
     ├─► Validate arguments  (Case.init_args_check)
     ├─► Configure VCG variables  (compset, grid, launch)
     ├─► Write grid input files  (hgrid, topo, vgrid, mesh)
     ├─► create_newcase
     ├─► Apply ntasks / queue / wallclock via xmlchange
     └─► Report required forcing configurators
```

You don't need to call any of these individually — instantiating `Case` runs the
whole sequence.

## Reading the "required configurators" message

After `Case(...)` succeeds, you'll see something like:

```
The following additional configuration options are required to run and must be
provided with any listed arguments in configure_forcings:
  - tides: tpxo_elevation_filepath, tpxo_velocity_filepath, tidal_constituents
  - initial_conditions: start_date
```

Each line is one configurator class plus the keyword arguments you'll need to
pass to `case.configure_forcings(...)` in the next step. See
[Configure Forcings](3a_configure_forcings.md) for the full story.

You can reproduce this list at any time:

```python
from CrocoDash.forcing_configurations import ForcingConfigRegistry
required = ForcingConfigRegistry.find_required_configurators(case.compset_lname)
```

## Compset properties on the `Case`

`Case` exposes a few convenience properties derived from your compset:

| Property | True when… |
|---|---|
| `case.cice_in_compset` | `"CICE"` appears in the compset longname |
| `case.runoff_in_compset` | `"SROF"` is **not** in the compset longname (i.e. active/data runoff) |
| `case.bgc_in_compset` | `"%MARBL"` appears in the compset longname |

These are handy for branching in user scripts and are also what the forcing
configurators use internally to decide which configurators are compatible.

## Common pitfalls

- **`Given caseroot ... already exists!`** — pass `override=True` *or* pick a fresh path. `override=True` is safe for iteration but will remove the prior case directory.
- **`compset must be a valid CESM compset long name or alias.`** — aliases are resolved against your CESM checkout's compset list. If the alias isn't in `self.cime.compsets`, you either have the wrong `cesmroot` or your CESM checkout doesn't include the CROCODILE compset fork.
- **Only MOM6-based compsets are supported.** CrocoDash enforces `MOM6`, `SLND`, `SGLC`, and `SWAV` in the compset longname. Active land/glacier/wave models are not supported.
- **Machine requires a project.** If your machine has accounting, `project=` is not optional.

## Next steps

- **[3a. Configure Forcings](3a_configure_forcings.md)** — declare the data your case needs
- **[3b. Process Forcings](3b_process_forcings.md)** — generate the forcing files
- **[Compsets & Inputs](compsets_and_inputs.md)** — reference for compset aliases and MOM6 parameter tuning

## See also

- [Submodule API Usage](../for_developers/submodule_api_usage.md) — exactly which VisualCaseGen/regional-mom6 entry points `Case` calls
