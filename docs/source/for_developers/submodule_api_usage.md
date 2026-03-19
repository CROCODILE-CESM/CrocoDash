# Submodule API Usage

CrocoDash depends on three submodules — `regional-mom6`, `mom6_bathy`, and `visualCaseGen` — which are developed and versioned independently. This page records exactly which functions and classes from each submodule CrocoDash calls. The purpose is to give developers a clear reference when those upstream repos change: if a function listed here is renamed, removed, or has its signature altered, CrocoDash will break. Keeping this record up to date makes it easy to catch those breaking changes before they land.

---

## regional-mom6

Imported as `import regional_mom6 as rmom6` / `rm6`.

| Function / Class | Called in | What CrocoDash uses it for |
|---|---|---|
| `rmom6.experiment(...)` | `case.py`, `extract_forcings/tides.py` | Constructs the main MOM6 experiment object with grid, date range, and depth parameters |
| `rmom6.experiment.create_empty(...)` | `extract_forcings/regrid_dataset_piecewise.py` | Creates a minimal experiment shell when a full experiment object is not needed |
| `expt.setup_boundary_tides(...)` | `extract_forcings/tides.py` | Generates tidal boundary conditions from tidal elevation and transport data |
| `rm6.segment(...)` | `extract_forcings/regrid_dataset_piecewise.py` | Creates a boundary segment object for regridding ocean state forcings |
| `rm6.segment(...).regrid_velocity_tracers` | `extract_forcings/regrid_dataset_piecewise.py` | Most important function for regridding OBCs |
| `rm6.regridding.fill_missing_data` | `extract_forcings/regrid_dataset_piecewise.py` | Passed as the fill method when regridding boundary forcing datasets |
| `rm6.rotation.RotationMethod.EXPAND_GRID` | `extract_forcings/regrid_dataset_piecewise.py` | Specifies the rotation method used when processing boundary segments |
| `rm6.get_glorys_data(...)` | `raw_data_access/datasets/glorys.py` | Downloads GLORYS ocean reanalysis data for use as initial/boundary conditions |

---

## mom6_bathy

Imported as `from mom6_bathy import ...` / `import mom6_bathy as m6b`.

| Function / Class | Called in | What CrocoDash uses it for |
|---|---|---|
| `Grid` (via `from mom6_bathy.grid import *`) | `grid.py` | Re-exported directly — CrocoDash exposes mom6_bathy's horizontal grid class as its own |
| `Topo` (via `from mom6_bathy.topo import *`) | `topo.py` | Re-exported directly — CrocoDash exposes mom6_bathy's bathymetry class as its own |
| `VGrid` (via `from mom6_bathy.vgrid import *`) | `vgrid.py` | Re-exported directly — CrocoDash exposes mom6_bathy's vertical grid class as its own |
| `GridCreator` (via `from mom6_bathy.grid_creator import *`) | `grid_creator.py` | Re-exported directly — interactive grid creation widget |
| `TopoEditor` (via `from mom6_bathy.topo_editor import *`) | `topo_editor.py` | Re-exported directly — interactive bathymetry editing widget |
| `VGridCreator` (via `from mom6_bathy.vgrid_creator import *`) | `vgrid_creator.py` | Re-exported directly — interactive vertical grid creation widget |
| `chl.interpolate_and_fill_seawifs(...)` | `extract_forcings/chlorophyll.py` | Interpolates and fills SeaWiFS chlorophyll data onto the ocean grid |
| `mapping.get_smoothed_map_filepath(...)` | `extract_forcings/runoff.py`, `forcing_configurations/configurations.py` | Generates smoothed runoff-to-ocean mapping file names |
| `mapping.<the_mapping_function>` | `extract_forcings/runoff.py`, `forcing_configurations/configurations.py` | Generates smoothed runoff-to-ocean mapping files |
| `utils.fill_missing_data(...)` | `extract_forcings/regrid_dataset_piecewise.py` | Fills missing values in ocean state fields during piecewise regridding |

---

## visualCaseGen

Imported as `from visualCaseGen import ...`.

| Function / Class | Called in | What CrocoDash uses it for |
|---|---|---|
| `initialize(...)` (imported as `initialize_visualCaseGen`) | `case.py` | Initialises the visualCaseGen GUI and CIME interface at case setup time |
| `CaseCreator` | `case.py` | Class that drives interactive CESM case creation |
| `ERROR`, `RESET` | `case.py` | Status enums used to check and reset the CaseCreator widget state |
| `xmlchange(...)` | `case.py`, `forcing_configurations/base.py` | Applies `xmlchange` commands to modify CESM XML configuration files |
| `append_user_nl(...)` | `case.py`, `forcing_configurations/base.py` | Appends entries to CESM `user_nl_*` namelist files |
