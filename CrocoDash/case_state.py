"""
case_state.py — Serialization policy and I/O for the CrocoDash case state file.

The case state is written to ``crocodash_state.json`` inside the case root at the
end of ``Case.__init__``.  This module owns:

- the schema version used to gate compatibility checks;
- which ``Case.__init__`` arguments are excluded from the state snapshot
  (``INIT_ARGS_EXCLUDE``);
- which state-file keys are *derived* (i.e. cannot be passed straight back to
  ``Case.__init__``) and therefore need explicit handling when reconstructing a
  case from the file (``DERIVED_KEYS``);
- the ``write``, ``read``, and ``check_version`` functions.

Keeping both ``INIT_ARGS_EXCLUDE`` and ``DERIVED_KEYS`` here makes the
serialisation contract visible and co-located: when the state schema changes,
this is the single file to update.
"""

import json
from pathlib import Path

from CrocoDash.logging import setup_logger

logger = setup_logger(__name__)

SCHEMA_VERSION = "1.0.0"
FILENAME = "crocodash_state.json"

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
    }
)


def check_version(state, state_path):
    """Raise ValueError if state's schema_version is incompatible with SCHEMA_VERSION.

    Only MAJOR.MINOR must match; a higher PATCH is acceptable.
    Logs a warning (rather than raising) when schema_version is absent entirely
    (pre-versioning cases).
    """
    version = state.get("schema_version")
    if version is None:
        logger.warning(
            f"{state_path}: no schema_version found; this case was created before "
            "state versioning was introduced. Compatibility is not guaranteed."
        )
        return
    try:
        parts = version.split(".")
        major, minor = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        raise ValueError(f"Invalid schema_version {version!r} in {state_path}.")
    sup_parts = SCHEMA_VERSION.split(".")
    sup_major, sup_minor = int(sup_parts[0]), int(sup_parts[1])
    if (major, minor) != (sup_major, sup_minor):
        raise ValueError(
            f"{state_path} has schema version {version!r} but this version of "
            f"CrocoDash supports {sup_major}.{sup_minor}.x. "
            "Recreate the case with the current version of CrocoDash."
        )


def write(caseroot, state):
    """Write *state* to crocodash_state.json, injecting schema_version as the first key."""
    full_state = {"schema_version": SCHEMA_VERSION, **state}
    with open(Path(caseroot) / FILENAME, "w") as f:
        json.dump(full_state, f, indent=2)


def read(caseroot):
    """Read crocodash_state.json, validate the schema version, and return the state dict."""
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
