# Command Line Interface

CrocoDash ships a `crocodash` command (installed automatically with `pip install -e .`) that lets you run the full case setup workflow from a YAML config file and inspect or share existing cases — no Python scripting required.

## Quick reference

```
crocodash create            --config mycase.yaml [--override]
crocodash dump              --caseroot /path/to/case
crocodash process  [--caseroot /path/to/case] [--all | --ic --bc ...]  [--skip ...]
crocodash bundle            --caseroot /path/to/case --output-dir /path/to/bundle_dir ...
crocodash fork              --bundle /path/to/bundle --caseroot ... --inputdir ... --cesmroot ... --machine ... --project ...
crocodash duplicate         --source /path/to/case --case /path/to/new_case --inputdir /path/to/new_inputdir
```

---

## `crocodash create`

Creates a new CrocoDash case end-to-end from a YAML config file. Equivalent to calling `recipe.create_case_from_yaml()`.

```bash
crocodash create --config mycase.yaml
crocodash create --config mycase.yaml --override   # overwrite existing caseroot/inputdir
```

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

# --- Forcings (required) ---
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

After `create` completes the caseroot contains a `crocodash_state.json` recording all construction parameters, and `inputdir/extract_forcings/config.json` recording the forcing setup. These files are the source of truth for `dump`, `bundle`, and `fork`.

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

# Run from inside the extract_forcings/ directory — no --caseroot needed
cd ~/scratch/croc_input/mycase/extract_forcings
crocodash process --all
```

### Flags

| Flag | Description |
|------|-------------|
| `--config PATH` | Direct path to `config.json`. Takes precedence over `--caseroot`. |
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

### Auto-detection

If you `cd` into `inputdir/extract_forcings/` (the directory that contains `config.json`), you can run `crocodash process` without specifying `--caseroot` — it finds `config.json` in the current directory automatically.

---

## `crocodash bundle`, `fork`, `duplicate`

For sharing cases with others, see [Shareable Configuration](shareable.md).
