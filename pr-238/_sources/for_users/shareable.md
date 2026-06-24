# Sharing Cases

The `CrocoDash.shareable` module lets you share a configured regional ocean case
with another user — across machines, institutions, or just between collaborators.

It sits on top of [recipe.py](cli.md), which handles programmatic case creation
from YAML. The shareable layer adds case inspection, bundling, and an interactive
guided review for the recipient.

---

## The model: sender and recipient

The **bundle folder** is the artifact that crosses the user boundary.

**Sender** (Person A, has a working case):
```
CaseBundle(caseroot)
  → identify_non_standard_case_info()   # what makes this case unique?
  → bundle(output_dir)                  # package everything up
```

**Recipient** (Person B, gets the bundle folder):
```
ForkBundle(bundle_dir)
  → fork(cesmroot, machine, ...)        # guided recreation on their machine
```

The recipient can change the compset or forcing configuration during `fork()` —
everything else (grid, bathymetry, vertical grid, non-standard CESM state) is
carried over from the bundle.

---

## Sender: CaseBundle

```python
from CrocoDash.shareable import CaseBundle

bundle = CaseBundle("/path/to/caseroot")

# Optionally inspect the diff before bundling
diff = bundle.identify_non_standard_case_info(
    cesmroot="/path/to/cesm",
    machine="derecho",
    project_number="PROJ123",
)
print(diff.xmlchanges_missing)
print(diff.source_mods_missing_files)

# Package everything into a portable folder
bundle_path = bundle.bundle("/path/to/output_dir")
```

`identify_non_standard_case_info()` creates a temporary reference case using
recipe.py (with `configure_only=True` so forcings are not re-processed), then
diffs your case against it. The diff captures everything you added on top of
what CrocoDash sets up by default:

| Category | What's captured |
|---|---|
| `xml_files_missing_in_new` | Extra `.xml` files in your caseroot |
| `user_nl_missing_params` | Parameters added to `user_nl_*` files |
| `source_mods_missing_files` | Files in `SourceMods/` |
| `xmlchanges_missing` | `xmlchange` calls in `replay.sh` |

`bundle()` calls `identify_non_standard_case_info()` automatically if you haven't
already. The bundle folder contains:

- `crocodash_case.yaml` — the full recipe (grid, topo, vgrid, case, forcings)
- `non_standard_case_info.json` — the diff
- `ocnice/` — all ocean/ice input files and grid files
- `user_nl_*`, `replay.sh`
- `xml_files/` and `SourceMods/` — any non-standard modifications

---

## Recipient: ForkBundle

```python
from CrocoDash.shareable import ForkBundle

fork = ForkBundle("/path/to/bundle")

case = fork.fork(
    cesmroot="/path/to/cesm",
    machine="derecho",
    project_number="PROJ123",
    new_caseroot="/path/to/new_case",
    new_inputdir="/path/to/new_inputdir",
)
```

`fork()` walks the recipient through an interactive review:

1. **Field review** — prompts for `caseroot`, `inputdir`, `cesmroot`, `machine`,
   `project`, `compset`, and (if the case has forcings) `date_range` and
   `boundaries`. Press Enter to keep the pre-filled value from the bundle.
2. **EDITOR** — if `$EDITOR` is set, offers to open the full YAML for deeper
   changes (e.g. swapping compset modifiers, adjusting forcing kwargs).
3. **Confirmation** — shows the final config and asks to proceed.
4. **Plan** — asks whether to transfer each category of non-standard CESM state
   (XML files, user_nl params, SourceMods, xmlchanges).

After confirmation, `fork()` recreates the case via recipe.py and applies the
non-standard state per the plan.

### Non-interactive fork

Pass `plan=` to skip the CESM-state copy prompts (the YAML review still runs):

```python
case = fork.fork(
    cesmroot="/path/to/cesm",
    machine="derecho",
    project_number="PROJ123",
    new_caseroot="/path/to/new_case",
    new_inputdir="/path/to/new_inputdir",
    plan={"xml_files": True, "user_nl": True, "source_mods": False, "xmlchanges": True},
)
```

---

## Duplicate (same-user shortcut)

For copying a case within your own environment — same machine, new paths — use
`duplicate_case()`. It reads `cesmroot`, `machine`, and `project` directly from
the original case's `crocodash_state.json`, so no arguments are needed for those:

```python
from CrocoDash.shareable import duplicate_case

new_case = duplicate_case(
    caseroot="/path/to/existing_case",
    new_caseroot="/path/to/new_case",
    new_inputdir="/path/to/new_inputdir",
)
```

Pass `bundle_dir=` to also save a bundle as a side effect:

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
# Interactive (guided YAML review + plan prompts)
crocodash fork \
  --bundle /path/to/bundle \
  --caseroot /path/to/new_case \
  --inputdir /path/to/new_inputdir \
  --cesmroot /path/to/cesm \
  --machine derecho \
  --project PROJ123

# Non-interactive plan (YAML review still runs)
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

## Apply helpers

The low-level transfer functions used by `ForkBundle` internally are importable
directly for fine-grained control:

```python
from CrocoDash.shareable import (
    copy_xml_files_from_case,
    copy_user_nl_params_from_case,
    copy_source_mods_from_case,
    apply_xmlchanges_to_case,
    copy_configurations_to_case,
)
```
