# Templates

The `crocodash template` command writes a ready-to-use starter file sourced from the gallery tutorial notebook. Use it as a starting point instead of writing from scratch. The `--kind` flag picks what you're generating:

- `--kind case` (default) — a case definition: config, notebook, or script
- `--kind pbs` — a PBS batch script for submitting forcing extraction to an HPC queue

---

## Case templates (`--kind case`)

```bash
# Jupyter notebook with <KEY> placeholders for manual editing
crocodash template --output my_case.ipynb

# Jupyter notebook with Derecho/GLADE paths pre-filled
crocodash template --output my_case.ipynb --machine derecho

# Python script with Derecho paths pre-filled
crocodash template --output my_case.py --machine derecho

# YAML config with Derecho paths pre-filled
crocodash template --output my_case.yaml --machine derecho
```

For `--kind case`, the output *format* is picked by `--output`'s suffix: `.yaml`/`.yml` for a config, `.ipynb` for a notebook, anything else for a `.py` script.

The `.py` output extracts code cells directly from the gallery tutorial notebook — no separate template file to maintain. Cell boundaries are marked with `# %%`, making the file compatible with Jupytext and VS Code interactive Python.

---

## PBS submission script (`--kind pbs`)

```bash
crocodash template --output submit_forcings.pbs --kind pbs --machine derecho
```

This writes a batch submission script that runs `crocodash process --caseroot <caseroot> --all` on an HPC queue (e.g. Derecho) instead of interactively — useful for long-running forcing extraction. Edit the `#PBS -A <PROJECT_CODE>` and `caseroot` placeholders, then submit with `qsub submit_forcings.pbs`.

---

## `--machine`

The `--machine` flag replaces `<KEY>` placeholders (e.g. `<GEBCO>`, `<CESM>`, `<inputdir>`) with real paths for the given machine. Omit it to leave placeholders and fill them in manually. Applies to both `--kind case` and `--kind pbs`.

---

## Available machines

Machine path registries are defined in `crocogallery/known_paths.json` inside the CrocoGallery repo. To add a new environment (e.g. `"casper"`, `"local"`, `"manish"`), add a new top-level key with the relevant path mappings — no Python changes needed.

Passing an unknown machine name prints the available options:

```
KeyError: Unknown machine 'bogus'. Available: derecho
```

---

## What gets filled in

| Placeholder | Description |
|---|---|
| `<GEBCO>` | GEBCO bathymetry file |
| `<TPXO_H>`, `<TPXO_U>` | TPXO tidal constituent files |
| `<CESM>` | Path to CESM source checkout |
| `<inputdir>` | Directory for model input files |
| `<casedir>` | Directory for the CESM case |
| `<CHL>` | Chlorophyll data file |
| `<MARBL_IC>` | MARBL BGC initial condition |
| ... | Other dataset paths in known_paths.json |
