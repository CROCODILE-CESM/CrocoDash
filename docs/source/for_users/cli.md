# Command Line Interface

CrocoDash ships a `crocodash` command (installed automatically with `pip install -e .`) that lets you run the full case setup workflow from a YAML config file and inspect or share existing cases — no Python scripting required.

## Quick reference

```
crocodash template          --output my_case.{yaml,ipynb,py,pbs} [--machine glade] [--notebook ID]
crocodash create            (--config mycase.yaml | --from /path/to/case_or_bundle) [--caseroot ...] [--override] [--no-input]
crocodash dump              --caseroot /path/to/case
crocodash configure         --caseroot /path/to/case [--config forcings.yaml] [--set key=value ...] [--no-input]
crocodash process  [--caseroot /path/to/case] [--all | --ic --bc ...]  [--skip ...] [--preview] [--force]
crocodash bundle            --caseroot /path/to/case --output-dir /path/to/bundle_dir
```

---

## `crocodash create`

Creates a new CrocoDash case end-to-end from a YAML config file. Equivalent to calling `recipe.create_case_from_yaml()`.

```bash
crocodash create --config mycase.yaml
crocodash create --config mycase.yaml --override   # overwrite existing caseroot/inputdir
```

Without a `forcings:` section, `create` asks for the forcings once the case exists,
as `crocodash configure` does (see [Being asked for the forcings](#being-asked-for-the-forcings)).
That needs a terminal: in a script, or with `--no-input`, a config without a `forcings:`
section is refused before anything is created.

`crocodash create --from` starts from an existing case or a bundle instead of a config;
see [Sharing and Copying Cases](sharing.md).

### YAML config schema

```yaml
# --- Horizontal grid ---
grid:
  lenx: 10.0           # domain width in degrees
  leny: 10.0           # domain height in degrees
  xstart: -60.0        # western edge longitude
  ystart: 30.0         # southern edge latitude
  resolution: 1.0      # degrees per cell (or use nx/ny instead)
  name: "mygrid"

# --- Bathymetry ---
topo:
  min_depth: 10.0      # columns shallower than this are masked
  source:
    type: "flat"           # flat | dataset | from_file
    depth: 1000.0          # for type: flat — constant depth in metres

    # type: dataset — interpolate from a real bathymetry file (e.g. GEBCO)
    # bathymetry_path: "/path/to/gebco.nc"
    # longitude_coordinate_name: "lon"
    # latitude_coordinate_name: "lat"
    # vertical_coordinate_name: "elevation"
    # is_input_positive_below_msl: false
    # fill_channels: false

    # type: from_file — reuse an existing topog.nc
    # topo_file_path: "/path/to/ocean_topog.nc"

# --- Vertical grid ---
vgrid:
  type: "uniform"      # uniform | hyperbolic | from_file
  nk: 10               # number of layers
  # depth omitted → uses topo.max_depth automatically
  name: "myvgrid"

  # type: hyperbolic — surface-intensified levels
  # nk: 75
  # depth: 5000.0
  # ratio: 20.0

  # type: from_file — reuse an existing vgrid.nc
  # filename: "/path/to/ocean_vgrid.nc"

# --- CESM case ---
case:
  cesmroot: "/path/to/CROCESM"
  caseroot: "/path/to/cases/mycase"
  inputdir:  "/path/to/croc_input/mycase"
  compset:   "CR_JRA"          # alias or full long name
  machine:   "derecho"
  project:   "NCGD0011"
  atm_grid_name: "TL319"       # optional, default TL319

# --- Forcings (left out: asked for on a terminal) ---
forcings:
  date_range: ["2020-01-01 00:00:00", "2020-02-01 00:00:00"]
  boundaries: ["south", "east", "west"]
  product_name: "GLORYS"
  function_name: "get_glorys_data_from_rda"

  # Any extra kwargs are forwarded directly to configure_forcings:
  # tidal_constituents: ["M2", "S2"]
  # tpxo_elevation_filepath: "/path/to/TPXO_elevation.nc"
  # tpxo_velocity_filepath:  "/path/to/TPXO_velocity.nc"
```

After `create` completes the caseroot contains a `_crocodash_state.json` recording all construction parameters, and `inputdir/extract_forcings/config.json` recording the forcing setup. These files are the source of truth for `dump`, `bundle` and `create --from`.

---

## `crocodash dump`

Prints a YAML representation of an existing case to stdout. The output can be saved, edited, and passed back to `create` — making `dump` the exact inverse of `create`.

```bash
# View the config for an existing case
crocodash dump --caseroot ~/croc_cases/mycase

# Save it to a file and edit before re-creating
crocodash dump --caseroot ~/croc_cases/mycase > mycase_copy.yaml
# ... edit paths, dates, machine, etc. ...
crocodash create --config mycase_copy.yaml --override
```

The dumped YAML uses `supergrid_path`/`from_file` references pointing at the existing grid/topo/vgrid files. To create a fully independent copy, either update those paths or re-generate the grid from parameters.

---

## `crocodash configure`

Configures the forcings of an existing case again, in place: no new case is created. It
starts from the arguments the case's forcings were configured with
(`case.forcing_args()`), applies the `forcings:` section of `--config` (a YAML file such
as one `crocodash dump` writes), then each `--set`, and calls `configure_forcings()`.
Arguments you don't change keep their values. Process the forcings again afterwards.

```bash
# Move the run to February
crocodash configure --caseroot ~/croc_cases/mycase \
    --set "date_range=['2020-02-01 00:00:00', '2020-03-01 00:00:00']"

# Keep only two boundaries, and take the rest from a YAML file
crocodash configure --caseroot ~/croc_cases/mycase --config forcings.yaml --set boundaries=[north,east]

crocodash process --caseroot ~/croc_cases/mycase --all
```

| Flag | Description |
|------|-------------|
| `--caseroot PATH` | The case to configure. |
| `--config PATH` | YAML file whose `forcings:` section replaces the matching arguments. |
| `--set KEY=VALUE` | Set one `configure_forcings()` argument, after `--config`. `VALUE` is read as YAML, so lists and numbers work; quote dates. Repeatable. |
| `--no-input` | Never ask, even on a terminal. |

A case whose forcings were never configured needs at least `date_range`.

### Being asked for the forcings

On a terminal, `crocodash configure` without `--config` or `--set` (and `crocodash
create` with a config that has no `forcings:` section) asks for the forcings:

1. It lists the forcings that are on for the case's compset (the ones it requires, and
   the ones it allows that need no input) and the optional ones.
2. It asks which optional forcings to add.
3. It asks each input of the chosen forcings, with a note on what it is and its choices.

Each question offers a value in brackets: the case's current one, or the default. Enter
keeps it; answers are read as YAML, so lists and numbers work. A required input without
a value has to be given. If the input ends (Ctrl-D, or a script's last line), the rest
keep the values offered, so a case is configured again unchanged. The same walkthrough
runs in Python with `case.configure_forcings(ask=True)`.

---

## `crocodash template`

Writes a ready-to-use starter file — a YAML config, a notebook, a Python script,
or a PBS submission script. See **[Templates](template.md)** for the full page.

```bash
crocodash template --output my_case.yaml --machine glade   # starter config
crocodash template --output my_case.ipynb --machine glade  # starter notebook
crocodash template --output submit_forcings.pbs            # PBS batch script
crocodash template --list-notebooks                        # available sources
```

| Flag | Description |
|------|-------------|
| `--output PATH` | Output path; its suffix picks the format. Required unless `--list-notebooks`. |
| `--kind {case,pbs}` | `case` (default) or `pbs`. A `.pbs` suffix selects `pbs` on its own. |
| `--machine NAME` | Pre-fill dataset paths for this machine (`glade`). Omit to leave `<KEY>` placeholders. |
| `--notebook ID` | Gallery notebook to render from (default `crocodash.tutorial-ocn`). |
| `--list-notebooks` | Print every available notebook ID and exit. |

---

## `crocodash process`

Runs the forcing extraction workflow for an existing CrocoDash case. This is equivalent to calling `case.process_forcings()` from Python, but can be invoked from any shell — including inside an HPC batch script.

```bash
# Run all configured forcing components
crocodash process --caseroot ~/croc_cases/mycase --all

# Run only specific components
crocodash process --caseroot ~/croc_cases/mycase --ic --bc

# Skip components even when running --all
crocodash process --caseroot ~/croc_cases/mycase --all --skip tides runoff

# See which components are finished or would run, and their files, without running anything
crocodash process --caseroot ~/croc_cases/mycase --all --preview

# Rerun components that are already finished
crocodash process --caseroot ~/croc_cases/mycase --bc --force

# Run from inside the extract_forcings/ directory — no --caseroot needed
cd ~/scratch/croc_input/mycase/extract_forcings
crocodash process --all
```

### Flags

| Flag | Description |
|------|-------------|
| `--config PATH` | Path to a case's `config.json`; that case is processed. Takes precedence over `--caseroot`. |
| `--caseroot PATH` | Path to the CESM caseroot. Defaults to cwd if omitted. |
| `--all` | Enable all components that are present in `config.json`. |
| `--ic` | Initial conditions. |
| `--bc` | Boundary conditions. |
| `--bgcic` | BGC initial conditions (requires BGC forcing configured). |
| `--bgcironforcing` | BGC iron forcing. |
| `--bgcrivernutrients` | BGC river nutrients. |
| `--runoff` | Runoff-to-ocean mapping. |
| `--tides` | Tidal forcing. |
| `--chl` | Chlorophyll processing. |
| `--skip NAME...` | Skip one or more components by name (case-insensitive). |
| `--preview` | List each selected component as `finished` or `would run`, with its files marked `present` or `missing`, without running anything. |
| `--force` | Rerun the selected components even when they are finished. |

A component that already ran with the current configuration, and whose files are all still there, is skipped. See [Process Forcings](3b_process_forcings.md#finished-components-are-skipped).

### Auto-detection

If you `cd` into `inputdir/extract_forcings/` (the directory that contains `config.json`), you can run `crocodash process` without specifying `--caseroot` — it finds `config.json` in the current directory automatically.

---

## `crocodash bundle`, `crocodash create --from`

To copy a case, here or on another machine, see [Sharing and Copying Cases](sharing.md).
