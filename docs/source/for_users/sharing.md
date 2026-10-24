# Sharing Cases

A configured case can be copied, on the same machine or to another user or
machine, in two steps:

1. **Bundle** it: `case.bundle(output_dir)` (or `crocodash bundle`) writes a
   folder holding everything needed to recreate it.
2. **Fork** it: `Case.fork(source, caseroot, inputdir)` (or `crocodash fork`)
   creates a new case from a bundle, or straight from a caseroot.

---

## Bundle

```python
from CrocoDash.case import Case

case = Case.from_caseroot("/path/to/caseroot")
case.bundle("/path/to/my_bundle")
```

The bundle is a folder:

| Path | What it holds |
|---|---|
| `bundle.json` | The bundle's schema version, and the caseroot, inputdir and machine of the case it was made from |
| `caseroot/` | `_crocodash_state.json`, `replay.sh`, every `user_nl_*` file, the top-level `*.xml` files and `SourceMods/` |
| `inputdir/` | `extract_forcings/config.json` and `finished_steps.json`; the grid, topography, vertical grid and ESMF mesh files; and every forcing file the case has made so far, at the same paths as in the case's inputdir |

`Case.from_caseroot()` reads a bundle like the case's caseroot. A bundle made by
an older CrocoDash (one with `crocodash_case.yaml` instead of `bundle.json`) is
refused: bundle the case again with this version, or create a case from the
bundle's `crocodash_case.yaml` with `crocodash create --config`.

---

## Fork

```python
from CrocoDash.case import Case

new_case = Case.fork(
    Case.from_caseroot("/path/to/my_bundle"),  # or a caseroot
    "/path/to/new_case",
    "/path/to/new_inputdir",
    cesmroot="/path/to/cesm",  # cesmroot, machine and project default to the source's
    machine="derecho",
    project="PROJ123",
    changes={"date_range": ["2020-01-01 00:00:00", "2020-02-01 00:00:00"]},
)
new_case.process_forcings()
```

`Case.fork()`:

1. Refuses a caseroot or inputdir that already exists, an inputdir inside the
   source's, and a caseroot with the source's name on the source's machine
   (CIME would give both cases the same build and run directories).
2. Creates the case with the source's grid, topography, vertical grid and
   compset (or `compset=`; give the forcing arguments it needs that the source
   lacks in `changes`). The grid files keep their names.
3. Makes the changes you made to the source after creating it: its xmlchanges
   (from `replay.sh`), its own `user_nl_*` lines, `SourceMods/` and extra
   `*.xml` files. On another machine, the PE layout, batch job, project and
   directory settings are left out. `CONTINUE_RUN`, `RESUBMIT`, `EXEROOT`,
   `RUNDIR` and `DOUT_S_ROOT` are always left out: the new case starts a run
   of its own, in its own directories.
4. Configures the forcings like the source's, with `changes` applied.
5. Copies the files of each forcing step the source finished whose settings
   are the same in the new case, and records those steps as finished.
   `process_forcings()` makes the others: after a change to the dates or the
   boundaries, say, the initial and boundary conditions.
6. Prints what it carried over and which steps are left to process.

`plan=` turns parts of this off. `"xmlchanges"`, `"user_nl"`, `"source_mods"`
and `"xml_files"` are True by default; `"forcing_files"` is `"matching"` (the
default, as above), `"all"` (copy every finished step's files, whatever changed)
or `"none"`:

```python
new_case = Case.fork(source, "/path/to/new_case", "/path/to/new_inputdir",
                     plan={"xmlchanges": False, "forcing_files": "none"})
```

---

## Copy a case on its own machine

Fork its caseroot: cesmroot, machine and project default to the source's.

```python
new_case = Case.fork(
    Case.from_caseroot("/path/to/existing_case"),
    "/path/to/new_case",
    "/path/to/new_inputdir",
)
```

---

## Command Line

### Bundle

```bash
crocodash bundle \
  --caseroot /path/to/case \
  --output-dir /path/to/output_dir
```

This writes `/path/to/output_dir/<case name>_case_bundle/`.

### Fork

`--source` is a caseroot or a bundle (`--bundle` is the same option):

```bash
crocodash fork --source /path/to/output_dir/mycase_case_bundle
```

On a terminal, fork asks for each value, offering the source's; Enter keeps it:

1. The new case: caseroot, inputdir, cesmroot, machine, project and compset.
2. Each `configure_forcings()` argument of that compset, with whether it is
   required, what it is and its choices. Answers are read as YAML, so
   `[north, east]` is a list.
3. Whether to carry over each kind of change you made to the source, and which
   of its forcing files to copy (`matching`, `all` or `none`).

Enter doesn't keep a caseroot or inputdir that already exists, a cesmroot or
forcing file path that isn't on this machine, or a required argument's empty
value: type one (the same path, if you mean it). At the end of input (Ctrl-D),
everything left keeps its default. Only the forcing arguments you change are
passed to `Case.fork()` as `changes`.

Flags give the defaults: `--caseroot`, `--inputdir`, `--cesmroot`, `--machine`,
`--project`, and `--plan` (a JSON object with the keys of `plan=` above, e.g.
`'{"xmlchanges": false, "forcing_files": "none"}'`). To fork without prompts
(not on a terminal, `--no-input` is the default):

```bash
# Take the source's value of everything else
crocodash fork --source /path/to/case --caseroot /path/to/new_case \
  --inputdir /path/to/new_inputdir --no-input

# Or write the fork to a YAML file, edit it, and fork from it
crocodash fork --source /path/to/case --write-yaml fork.yaml
crocodash fork --config fork.yaml
```

The YAML has `source:`, `case:`, `forcings:` and `plan:` sections. Each forcing
argument has a comment saying whether it is required, what it is, its choices,
and whether it is a path (on the source machine); the ones the source doesn't
set are listed commented out. `crocodash dump --annotate` writes a case's
forcings the same way.
