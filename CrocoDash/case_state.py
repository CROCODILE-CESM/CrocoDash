"""
case_state.py — Serialization policy and I/O for the CrocoDash case state file.

The case state is written to ``_crocodash_state.json`` inside the case root at the
end of ``Case.__init__``.  This module owns:

- the schema version used to gate compatibility checks;
- which ``Case.__init__`` arguments are excluded from the state snapshot
  (``INIT_ARGS_EXCLUDE``);
- which state-file keys are *derived* (i.e. cannot be passed straight back to
  ``Case.__init__``) and therefore need explicit handling when reconstructing a
  case from the file (``DERIVED_KEYS``);
- the ``created`` snapshot of what creating the case left in the caseroot, and
  ``parse_xmlchanges``, which reads the xmlchanges in replay.sh beyond it;
- the ``write``, ``read``, and ``check_version`` functions.

Keeping both ``INIT_ARGS_EXCLUDE`` and ``DERIVED_KEYS`` here makes the
serialisation contract visible and co-located: when the state schema changes,
this is the single file to update.
"""

import json
import re
import shlex
from pathlib import Path

# 1.2.0 added esmf_mesh_path and created. Older state files are refused: the
# case has to be recreated (there is no migration).
SCHEMA_VERSION = "1.2.0"
FILENAME = "_crocodash_state.json"

# Keys from Case.__init__ locals() that are NOT stored in _init_args.
# Objects (stored as paths), args resolved to derived values, and ephemeral flags.
INIT_ARGS_EXCLUDE = frozenset(
    {
        "self",
        "ocn_grid",
        "ocn_topo",
        "ocn_vgrid",
        "compset",
        "machine",
        "cesmroot",
        "caseroot",
        "inputdir",
        "override",
        "session_id",
    }
)

# Keys written into the state file as derived/resolved fields.
# These cannot be passed straight back to Case.__init__ — they require explicit
# handling when reconstructing a case from the file (e.g. in case_to_yaml).
# Must stay in sync with the derived block in case_state.write() callers and
# "schema_version" which is injected automatically by write().
DERIVED_KEYS = frozenset(
    {
        "schema_version",
        "inputdir",
        "cesmroot",
        "supergrid_path",
        "topo_path",
        "vgrid_path",
        "grid_name",
        "session_id",
        "compset_lname",
        "machine",
        "esmf_mesh_path",
        "created",
    }
)


def created_snapshot(caseroot):
    """What creating the case left in *caseroot*, stored as the state's
    "created" entry: anything beyond it is a change the user made later."""
    caseroot = Path(caseroot)
    replay = caseroot / "replay.sh"
    return {
        "replay_lines": (
            len(replay.read_text().splitlines()) if replay.exists() else 0
        ),
        "user_nl": {
            path.name: path.read_text() for path in sorted(caseroot.glob("user_nl_*"))
        },
        "xml_files": sorted(path.name for path in caseroot.glob("*.xml")),
    }


# The xmlchange options that take a value, without their leading dashes.
_XMLCHANGE_VALUE_OPTIONS = {
    "caseroot",
    "subgroup",
    "id",
    "val",
    "file",
    "delimiter",
    "loglevel",
}


def parse_xmlchanges(lines):
    """{variable: last value set} by the xmlchange commands among replay.sh's
    ``lines``.

    Reads every form CIME records: ``./xmlchange`` or a path to it;
    ``K=V``, ``K1=V1,K2=V2`` (or split by ``--delimiter``) and ``--id K --val V``
    (also ``--id=K``); quoted values; and flags such as ``--force``,
    ``--non-local`` or ``--file F``. A ``--dryrun`` line changes nothing, and an
    ``--append`` one adds to a value that can't be known here, so both are
    skipped, as are lines that aren't valid shell.
    """
    changes = {}
    for line in lines:
        try:
            words = shlex.split(line, comments=True)
        except ValueError:
            continue
        if not words or Path(words[0]).name != "xmlchange":
            continue
        options, settings = {}, []
        words = iter(words[1:])
        for word in words:
            if not word.startswith("-"):
                settings.append(word)
                continue
            name, has_value, value = word.lstrip("-").partition("=")
            if name in _XMLCHANGE_VALUE_OPTIONS and not has_value:
                value = next(words, "")
            options[name] = value
        if "dryrun" in options or "append" in options:
            continue
        if "id" in options:
            changes[options["id"]] = options.get("val", "")
        split = r"(?<!\\)" + re.escape(options.get("delimiter") or ",")
        for setting in settings:
            for pair in re.split(split, setting):
                var, is_setting, value = pair.partition("=")
                if is_setting:
                    changes[var.strip()] = value
    return changes


def check_version(state, state_path, supported=SCHEMA_VERSION):
    """Raise ValueError if state's schema_version is incompatible with *supported*.

    Only MAJOR.MINOR must match; a higher PATCH is acceptable. A state file
    without a schema_version predates versioning and is refused too. Also used
    for the forcing config.json (see CrocoDash.forcing.base.read_config), which
    passes its own *supported* and reads an unversioned file as 1.0.0.
    """
    version = state.get("schema_version")
    if version is None:
        raise ValueError(
            f"{state_path} has no schema_version, so an older version of "
            "CrocoDash created it. Recreate the case with the current version "
            "of CrocoDash."
        )
    try:
        parts = version.split(".")
        major, minor = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        raise ValueError(f"Invalid schema_version {version!r} in {state_path}.")
    sup_parts = supported.split(".")
    sup_major, sup_minor = int(sup_parts[0]), int(sup_parts[1])
    if (major, minor) != (sup_major, sup_minor):
        raise ValueError(
            f"{state_path} has schema version {version!r} but this version of "
            f"CrocoDash supports {sup_major}.{sup_minor}.x. "
            "Recreate the case with the current version of CrocoDash."
        )


def write(caseroot, state):
    """Write *state* to _crocodash_state.json, injecting schema_version as the first key."""
    full_state = {"schema_version": SCHEMA_VERSION, **state}
    with open(Path(caseroot) / FILENAME, "w") as f:
        json.dump(full_state, f, indent=2)


def read(caseroot):
    """Read _crocodash_state.json, validate the schema version, and return the state dict."""
    path = Path(caseroot) / FILENAME
    if not path.exists():
        raise FileNotFoundError(
            f"No {FILENAME} found in {caseroot}. "
            "This case may not have been created with a recent version of CrocoDash."
        )
    with open(path) as f:
        state = json.load(f)
    check_version(state, path)
    return state
