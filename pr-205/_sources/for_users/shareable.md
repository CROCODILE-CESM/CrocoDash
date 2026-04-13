# Shareable Configuration

Ever wanted to share your regional MOM6 setup? Get a summary of your unique changes? Let someone else easily run your model? This module is for you!

Importable through `CrocoDash.shareable`, the module lets you:

1. **Read** - Inspect an existing CESM case and identify what makes it unique
2. **Bundle** - Package that unique information into a portable folder
3. **Fork** - Recreate a case from a bundle, with optional modifications
4. **Clone** - One-step shortcut to copy a case to a new location, reading machine/project/cesmroot automatically from the original

---

## Workflow

### Step 1 — Read & Bundle

```python
from CrocoDash.shareable.inspect import ReadCrocoDashCase

case = ReadCrocoDashCase("/path/to/caseroot")

# Write the bundle — automatically diffs against a standard case first
bundle_path = case.bundle("/path/to/output_dir")
```

If you need to override the machine or project used for the diff (e.g. generating a bundle on a different machine than the original), pass them explicitly:

```python
bundle_path = case.bundle("/path/to/output_dir", machine="derecho", project="PROJ123")
```

The bundle folder contains:
- `manifest.json` — grid paths, forcing config, all case metadata
- `non_standard_case_info.json` — diff against a standard case
- `ocnice/` — ocean/ice input files plus grid files
- `user_nl_*` files, `replay.sh`
- `xml_files/` and `SourceMods/` — any non-standard modifications

### Step 2 — Fork

```python
from CrocoDash.shareable.fork import ForkCrocoDashBundle

forker = ForkCrocoDashBundle(
    bundle_location="/path/to/bundle",
    cesmroot="/path/to/cesm",
    machine="derecho",
    project_number="PROJ123",
    new_caseroot="/path/to/new_case",
    new_inputdir="/path/to/new_inputdir",
)

case = forker.fork()
```

By default `fork()` is interactive — it will ask you which non-standard items to copy over (XML files, user_nl params, SourceMods, xmlchanges) and whether you want to change the compset.

#### Non-interactive fork

All prompts can be bypassed by passing arguments directly:

```python
case = forker.fork(
    plan={"xml_files": True, "user_nl": True, "source_mods": False, "xmlchanges": True},
    compset="GOMOM6",                          # omit to keep the bundle's compset
    extra_configs=["tides"],                   # additional forcing configs to add
    remove_configs=["bgc"],                    # forcing configs to drop
    extra_forcing_args_path="/path/to/args.json",  # only needed if adding new configs
)
```

Any argument left as `None` (the default) will still prompt interactively, so you can pre-supply only some of them.

### Clone (one-step shortcut)

If you just want an exact copy of an existing case without any modifications, use `clone`. It reads machine, project, and cesmroot directly from the original caseroot — no extra arguments needed.

```python
from CrocoDash.shareable.inspect import clone

new_case = clone(
    caseroot="/path/to/existing_case",
    new_caseroot="/path/to/new_case",
    new_inputdir="/path/to/new_inputdir",
)
```

The bundle is written into `new_caseroot` and kept there after cloning. You can also specify a custom location:

```python
new_case = clone(
    caseroot="/path/to/existing_case",
    new_caseroot="/path/to/new_case",
    new_inputdir="/path/to/new_inputdir",
    bundle_dir="/path/to/bundle",
)
```

---

## Command Line

After installing CrocoDash (`pip install -e .`), a `crocodash` command is available.

### Read

```bash
crocodash read \
  --caseroot /path/to/case \
  --output-dir /path/to/bundle_dir \
  --cesmroot /path/to/cesm \
  --machine derecho \
  --project PROJ123
```

### Fork

```bash
# Interactive
crocodash fork \
  --bundle /path/to/bundle \
  --caseroot /path/to/new_case \
  --inputdir /path/to/new_inputdir \
  --cesmroot /path/to/cesm \
  --machine derecho \
  --project PROJ123

# Non-interactive
crocodash fork \
  --bundle /path/to/bundle \
  --caseroot /path/to/new_case \
  --inputdir /path/to/new_inputdir \
  --cesmroot /path/to/cesm \
  --machine derecho \
  --project PROJ123 \
  --plan '{"xml_files": true, "user_nl": true, "source_mods": false, "xmlchanges": true}' \
  --compset GOMOM6 \
  --extra-configs tides,bgc \
  --remove-configs runoff \
  --extra-forcing-args /path/to/args.json
```

All `fork` flags beyond the six required ones are optional and only needed to bypass the interactive prompts.

### Clone

```bash
crocodash clone \
  --clone /path/to/existing_case \
  --case /path/to/new_case \
  --inputdir /path/to/new_inputdir
```

Machine, project, and cesmroot are read automatically from the original case. Optionally specify where to keep the bundle:

```bash
crocodash clone \
  --clone /path/to/existing_case \
  --case /path/to/new_case \
  --inputdir /path/to/new_inputdir \
  --bundle-dir /path/to/bundle
```

---

## What gets diffed?

`identify_non_standard_CrocoDash_case_information` creates a temporary standard case with the same grid, topo, and forcing configuration, then diffs your case against it. The diff captures:

- XML files present in your case but not in the standard one
- `user_nl_*` parameters added on top of defaults
- `xmlchange` commands in `replay.sh` not present by default
- Files in `SourceMods/`

---

## Apply helpers

`CrocoDash.shareable.apply` contains the low-level functions used by Fork internally. Savvy users can call these directly to transfer individual pieces of one case to another:

```python
from CrocoDash.shareable.apply import (
    copy_xml_files_from_case,
    copy_user_nl_params_from_case,
    copy_source_mods_from_case,
    apply_xmlchanges_to_case,
    copy_configurations_to_case,
)
```
