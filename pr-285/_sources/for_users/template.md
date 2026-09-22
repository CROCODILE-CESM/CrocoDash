# Templates

The `crocodash template` command writes a ready-to-use starter file sourced from the gallery tutorial notebook. Use it as a starting point instead of writing from scratch. The `--kind` flag picks what you're generating:

- `--kind case` (default) — a case definition: config, notebook, or script
- `--kind pbs` — a PBS batch script for submitting forcing extraction to an HPC queue

---

## Case templates (`--kind case`)

```bash
# Jupyter notebook with <KEY> placeholders for manual editing
crocodash template --output my_case.ipynb

# Jupyter notebook with GLADE (Derecho/Casper) paths pre-filled
crocodash template --output my_case.ipynb --machine glade

# Python script with GLADE paths pre-filled
crocodash template --output my_case.py --machine glade

# YAML config with GLADE paths pre-filled
crocodash template --output my_case.yaml --machine glade

# Start from a different gallery notebook instead of the default tutorial
crocodash template --output my_marbl_case.ipynb --machine glade \
  --notebook crocodash.projects.marbl

# See every notebook you can start from
crocodash template --list-notebooks
```

For `--kind case`, the output *format* is picked by `--output`'s suffix: `.yaml`/`.yml` for a config, `.ipynb` for a notebook, anything else for a `.py` script.

The `.py` output extracts code cells directly from the gallery tutorial notebook — no separate template file to maintain. Cell boundaries are marked with `# %%`, making the file compatible with Jupytext and VS Code interactive Python.

---

## PBS submission script (`--kind pbs`)

```bash
crocodash template --output submit_forcings.pbs
```

A `.pbs` output suffix selects the PBS template on its own, the same way `.yaml`/`.ipynb` do for `--kind case` — `--kind pbs` is only needed if you want a different output filename. This writes a batch submission script that runs `crocodash process --caseroot <caseroot> --all` on an HPC queue (e.g. Derecho) instead of interactively — useful for long-running forcing extraction. Edit the `#PBS -A <PROJECT_CODE>` and `caseroot` placeholders, then submit with `qsub submit_forcings.pbs`.

---

## `--machine`

The `--machine` flag replaces `<KEY>` placeholders (e.g. `<GEBCO>`, `<TPXO_H>`) with real dataset paths for the given machine. The only registry shipped today is `glade`, which covers both Derecho and Casper. Omit the flag to leave placeholders and fill them in manually. It only applies to `--kind case` — the pbs template's placeholders (`<PROJECT_CODE>`, `caseroot`) aren't dataset paths, so `--machine` has no effect on `--kind pbs` output.

A few `known_paths.json` keys (`CESM`, `inputdir`, `casedir`) are also placeholder tokens rather than real paths, so they're always left as `<KEY>` for manual editing regardless of `--machine`.

---

## `--notebook` and `--list-notebooks`

`--kind case` templates are rendered from a **gallery notebook**, so you can
start from any of them rather than just the default tutorial
(`crocodash.tutorial`):

```bash
crocodash template --list-notebooks          # print every available ID
crocodash template --output my_case.ipynb --notebook crocodash.projects.ww3
```

IDs are the notebook's path in the CrocoGallery repo with `/` replaced by `.`
and the extension dropped — `crocodash/projects/marbl.ipynb` is
`crocodash.projects.marbl`.

`--notebook` only affects `--kind case` output formats that are rendered from a
notebook (`.ipynb` and `.py`). For `.yaml` and for `--kind pbs`, the template is
a standalone file and `--notebook` is ignored, with a message saying so.

`--output` is required unless you pass `--list-notebooks`.

---

## Available machines

Machine path registries are defined in `crocogallery/known_paths.json` inside the CrocoGallery repo. Today there is one: `glade`. To add a new environment (e.g. `"local"`, `"perlmutter"`), add a new top-level key with the relevant path mappings — no Python changes needed.

Passing an unknown machine name prints the available options:

```
KeyError: Unknown machine 'bogus'. Available: glade
```

---

## What gets filled in

| Placeholder | Description |
|---|---|
| `<GEBCO>` | GEBCO bathymetry file |
| `<TPXO_H>`, `<TPXO_U>` | TPXO tidal constituent files |
| `<CHL>` | Chlorophyll data file |
| `<MARBL_IC>` | MARBL BGC initial condition |
| ... | Other dataset paths in known_paths.json |

`<CESM>`, `<inputdir>`, and `<casedir>` are never filled in — always edit those manually.
