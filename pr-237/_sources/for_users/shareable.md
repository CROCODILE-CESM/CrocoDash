# Shareable Configuration

Ever wanted to share your regional MOM6 setup? Get a summary of your unique changes? Let someone else easily run your model? This module is for you!

Importable through `CrocoDash.shareable`, the module lets you:

1. **Bundle** - Inspect an existing CESM case, identify what makes it unique, and package it into a portable folder
2. **Fork** - Recreate a case from a bundle, guided through any changes via an interactive YAML review
3. **Duplicate** - One-step shortcut to copy a case to a new location, reading machine/project/cesmroot automatically from the original

The shareable workflow is built on top of the [`create`/`dump` primitives](cli.md): `bundle` uses `dump` internally to write the case config as `crocodash_case.yaml`, and `fork` uses `create` internally to build the new case from (a modified copy of) that YAML.

---

## Workflow

### Step 1 — Bundle

```python
from CrocoDash.shareable.bundle import BundleCrocoDashCase

case = BundleCrocoDashCase("/path/to/caseroot")

# Write the bundle — automatically diffs against a standard case first
bundle_path = case.bundle("/path/to/output_dir")
```

The bundle folder contains:
- `crocodash_case.yaml` — complete case config (grid, topo, vgrid, case, forcings)
- `non_standard_case_info.json` — diff against a standard case (user_nl, xmlchanges, xml_files, SourceMods)
- `ocnice/` — ocean/ice input files plus grid files
- `user_nl_*` files, `replay.sh`
- `xml_files/` and `SourceMods/` — any non-standard modifications

### Step 2 — Fork

```python
from CrocoDash.shareable.fork import ForkCrocoDashBundle

forker = ForkCrocoDashBundle("/path/to/bundle")

case = forker.fork(
    cesmroot="/path/to/cesm",
    machine="derecho",
    project_number="PROJ123",
    new_caseroot="/path/to/new_case",
    new_inputdir="/path/to/new_inputdir",
)
```

`fork()` guides you through the key fields interactively:

1. **Path and machine review** — prompts for `caseroot`, `inputdir`, `cesmroot`, `machine`, `project`, `compset`, and (if forcings were configured) `date_range` and `boundaries`. Press Enter to keep the pre-filled value.
2. **EDITOR** — if `$EDITOR` is set, offers to open the full YAML for deeper modifications (changing forcing kwargs, compset modifiers, etc.).
3. **Confirmation** — shows the final config and asks to proceed.
4. **Plan** — asks interactively which non-standard CESM state to copy (XML files, user_nl params, SourceMods, xmlchanges). Pass `plan=` to skip the prompts.

#### Non-interactive fork

```python
case = forker.fork(
    cesmroot="/path/to/cesm",
    machine="derecho",
    project_number="PROJ123",
    new_caseroot="/path/to/new_case",
    new_inputdir="/path/to/new_inputdir",
    plan={"xml_files": True, "user_nl": True, "source_mods": False, "xmlchanges": True},
)
```

To change forcings, compset, or other parameters: run `crocodash dump` on the bundle's YAML, edit it, and pass it to `crocodash create` directly — no need to use fork for that.

### Duplicate (one-step shortcut)

```python
from CrocoDash.shareable.bundle import duplicate_case

new_case = duplicate_case(
    caseroot="/path/to/existing_case",
    new_caseroot="/path/to/new_case",
    new_inputdir="/path/to/new_inputdir",
)
```

Reads machine, project, and cesmroot from `crocodash_state.json` in the original case. Pass `bundle_dir=` to save the bundle for reference:

```python
new_case = duplicate_case(
    caseroot="/path/to/existing_case",
    new_caseroot="/path/to/new_case",
    new_inputdir="/path/to/new_inputdir",
    bundle_dir="/path/to/bundle",
)
```

---

## Command Line

### Bundle

```bash
crocodash bundle \
  --caseroot /path/to/case \
  --output-dir /path/to/bundle_dir \
  --cesmroot /path/to/cesm \
  --machine derecho \
  --project PROJ123
```

### Fork

```bash
# Interactive (guided YAML review)
crocodash fork \
  --bundle /path/to/bundle \
  --caseroot /path/to/new_case \
  --inputdir /path/to/new_inputdir \
  --cesmroot /path/to/cesm \
  --machine derecho \
  --project PROJ123

# Non-interactive (skip CESM-state copy prompts)
crocodash fork \
  --bundle /path/to/bundle \
  --caseroot /path/to/new_case \
  --inputdir /path/to/new_inputdir \
  --cesmroot /path/to/cesm \
  --machine derecho \
  --project PROJ123 \
  --plan '{"xml_files": true, "user_nl": true, "source_mods": false, "xmlchanges": true}'
```

### Duplicate

```bash
crocodash duplicate \
  --source /path/to/existing_case \
  --case /path/to/new_case \
  --inputdir /path/to/new_inputdir
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
