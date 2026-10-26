# Sharing and Copying Cases

A configured case can be copied, on the same machine or to another user or
machine:

1. **Bundle** it, to move it elsewhere: `crocodash bundle` (or
   `case.bundle(output_dir)`) writes a folder holding everything needed to
   recreate it.
2. **Create a case from it**: `crocodash create --from` a bundle, or straight
   from a caseroot.

---

## Bundle

```bash
crocodash bundle --caseroot /path/to/case --output-dir /path/to/output_dir
```

This writes `/path/to/output_dir/<case name>_case_bundle/`. In Python:

```python
from CrocoDash.case import Case

Case.from_caseroot("/path/to/caseroot").bundle("/path/to/my_bundle")
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

## Create a case from another

```bash
crocodash create --from /path/to/output_dir/mycase_case_bundle   # or a caseroot
```

On a terminal, it asks for the new case's caseroot, inputdir, cesmroot,
machine, project and compset, offering the source's (a caseroot or inputdir
that exists has to be changed). Once the case exists, it walks through the
forcings, offering the source's (see
[Being asked for the forcings](cli.md#being-asked-for-the-forcings)). In a
script, give the new case's fields as flags and add `--no-input`:

```bash
crocodash create --from /path/to/output_dir/mycase_case_bundle --no-input \
  --caseroot /path/to/new_case --inputdir /path/to/new_inputdir \
  --cesmroot /path/to/cesm --machine derecho --project PROJ123
```

The new case:

1. Is refused if its inputdir is inside the source's, or if it has the source's
   name on the source's machine (CIME would give both cases the same build and
   run directories).
2. Gets the source's grid, topography, vertical grid and compset, and its
   session id, so the grid files keep their names. On the same machine it also
   gets the source's PE layout and batch job.
3. Gets the changes you made to the source after creating it: its xmlchanges
   (from `replay.sh`), its own `user_nl_*` lines, `SourceMods/` and extra
   `*.xml` files. On another machine, the PE layout, batch job, project and
   directory settings are left out. `CONTINUE_RUN`, `RESUBMIT`, `EXEROOT`,
   `RUNDIR` and `DOUT_S_ROOT` are always left out: the new case starts a run
   of its own, in its own directories.
4. Has its forcings configured like the source's, or as you answered.
5. Gets a copy of the files of each forcing step the source finished whose
   settings are the same in the new case; those steps are recorded as
   finished. Processing makes the others (after a change to the dates or the
   boundaries, say, the initial and boundary conditions). `create` processes
   the forcings unless `--configure-only` is given.

It prints what it carried over and which steps' files it copied.

In Python, the same:

```python
from CrocoDash.case import Case
from CrocoDash.recipe import case_to_yaml, create_case_from_yaml

source = Case.from_caseroot("/path/to/output_dir/mycase_case_bundle")
config = case_to_yaml(source)
config["case"] |= {"caseroot": "/path/to/new_case", "inputdir": "/path/to/new_inputdir"}
config["forcings"]["date_range"] = ["2020-02-01 00:00:00", "2020-03-01 00:00:00"]
new_case = create_case_from_yaml(config, source=source)
```
