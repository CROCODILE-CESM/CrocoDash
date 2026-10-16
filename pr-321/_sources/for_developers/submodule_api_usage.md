# Submodule API Usage

CrocoDash depends on three submodules — `regional-mom6`, `mom6_forge`, and `visualCaseGen` — which are developed and versioned independently. This page records exactly which functions and classes from each submodule CrocoDash calls. The purpose is to give developers a clear reference when those upstream repos change: if a function listed here is renamed, removed, or has its signature altered, CrocoDash will break. Keeping this record up to date makes it easy to catch those breaking changes before they land.

---

## regional-mom6

Imported as `import regional_mom6 as rmom6` / `rm6`.

| Function / Class | Called in | What CrocoDash uses it for |
|---|---|---|
| `rmom6.experiment(...)` | `case.py`, `forcing/tides.py` | Constructs the main MOM6 experiment object with grid, date range, and depth parameters |
| `rm6.experiment.create_empty(...)` | `forcing/mom6.py` | Creates a minimal experiment shell when a full experiment object is not needed |
| `expt.setup_boundary_tides(...)` | `forcing/tides.py` | Generates tidal boundary conditions from tidal elevation and transport data |
| `regional_mom6.segment.Segment(...)` | `forcing/mom6.py` | Creates a boundary segment object for regridding ocean state forcings |
| `Segment.regrid_velocity_tracers(...)` | `forcing/mom6.py` | Most important function for regridding OBCs |
| `Segment._regridders` | `forcing/mom6.py` | Cached regridder weights, read back out and fed to the next chunk via `regrid_velocity_tracers(regridders=...)` |
| `rm6.regridding.fill_missing_data` | `forcing/mom6.py` | Passed as the fill method when regridding boundary forcing datasets |
| `regional_mom6.chl.interpolate_and_fill_seawifs(...)` | `forcing/chl.py` | Interpolates and fills SeaWiFS chlorophyll data onto the ocean grid |
| `rm6.get_glorys_data(...)` | `raw_data_access/datasets/glorys.py` | Downloads GLORYS ocean reanalysis data for use as initial/boundary conditions |

---

## mom6_forge

Imported as `from mom6_forge import ...` / `import mom6_forge as m6b`.

| Function / Class | Called in | What CrocoDash uses it for |
|---|---|---|
| `Grid` (via `from mom6_forge.grid import *`) | `grid.py` | Re-exported directly — CrocoDash exposes mom6_forge's horizontal grid class as its own |
| `Topo` (via `from mom6_forge.topo import *`) | `topo.py` | Re-exported directly — CrocoDash exposes mom6_forge's bathymetry class as its own |
| `VGrid` (via `from mom6_forge.vgrid import *`) | `vgrid.py` | Re-exported directly — CrocoDash exposes mom6_forge's vertical grid class as its own |
| `GridCreator` (via `from mom6_forge.grid_creator import *`) | `grid_creator.py` | Re-exported directly — interactive grid creation widget |
| `TopoEditor` (via `from mom6_forge.topo_editor import *`) | `topo_editor.py` | Re-exported directly — interactive bathymetry editing widget |
| `VGridCreator` (via `from mom6_forge.vgrid_creator import *`) | `vgrid_creator.py` | Re-exported directly — interactive vertical grid creation widget |
| `Grid.write_supergrid(...)` | `case.py` | Writes the MOM6 supergrid file |
| `VGrid.write(...)` | `case.py` | Writes the MOM6 vertical grid file |
| `Topo.write_topo` / `write_scrip_grid` / `write_esmf_mesh` | `case.py` | Writes the MOM6 topography, SCRIP grid, and ESMF mesh files CESM needs |
| `Topo.write_cice_grid(...)` | `case.py` | Writes the CICE grid file when CICE is in the compset |
| `Topo.write_ww3_input(...)` | `case.py` | Writes WW3's grid-preprocessor `.inp` files when WW3 is in the compset |
| `mapping.get_suggested_smoothing_params(...)` | `forcing/runoff.py` | Derives `rmax`/`fold` from the ocean mesh resolution when the user omits them |
| `mapping.get_smoothed_map_filepath(...)` | `forcing/runoff.py` | Generates smoothed runoff-to-ocean mapping file names |
| `mapping.gen_rof_maps(...)` | `forcing/runoff.py` | Generates the smoothed runoff-to-ocean mapping files |
| `utils.fill_missing_data(...)` | `forcing/mom6.py` | Fills missing values in ocean state fields during regridding |
| `utils.longitude_slicer(...)` | `raw_data_access/datasets/glorys.py` | Slices a global dataset across the antimeridian for the requested bounding box |

---

## visualCaseGen

Imported as `from visualCaseGen import ...`. CrocoDash also reaches into
`ProConPy`, visualCaseGen's constraint-solver layer.

| Function / Class | Called in | What CrocoDash uses it for |
|---|---|---|
| `initialize(...)` (imported as `initialize_visualCaseGen`) | `case.py` | Initialises the visualCaseGen GUI and CIME interface at case setup time |
| `CaseCreator` | `case.py` | Class that drives interactive CESM case creation |
| `ERROR`, `RESET` | `case.py` | Status enums used to check and reset the CaseCreator widget state |
| `xmlchange(...)` | `case.py`, `forcing/base.py`, `shareable.py` | Applies `xmlchange` commands to modify CESM XML configuration files |
| `append_user_nl(...)` | `forcing/base.py`, `forcing/atm.py`, `shareable.py` | Appends entries to CESM `user_nl_*` namelist files |
| `ProConPy.config_var.ConfigVar`, `cvars` | `case.py`, `forcing/runoff.py` | Reads and sets visualCaseGen config variables (compset, grid, `MB_ATTEMPT_ID`, …) |
| `ProConPy.stage.Stage` | `case.py` | Advances visualCaseGen through its configuration stages |
| `ProConPy.dev_utils.ConstraintViolation` | `case.py` | Caught to turn solver constraint failures into CrocoDash-level errors |
