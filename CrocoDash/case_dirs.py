"""
case_dirs.py -- Replacing a case's directories without losing the previous case.

``Case.__init__`` writes to three directories: the input dir, the caseroot, and
CIME's build/run dir. ``CaseDirs`` takes care of whatever is already at those
paths, so that a failed or interrupted create never leaves the user with
neither the old case nor the new one.
"""

import os
import shutil
import uuid
from pathlib import Path


class CaseDirs:
    """The input dir, caseroot, and CIME build/run dir a new Case writes to.

    With override=True, an earlier case's copies are moved aside rather than
    deleted, so a failed re-create can put them back: undo() removes what
    the failed attempt wrote and restores them, discard_previous() deletes
    them once the new case is complete. A dir that already exists and is not
    moved aside (the build/run dir with override=False, which create_newcase
    refuses to reuse) is never touched.

    The paths may coincide or nest: a caseroot placed directly in
    CIME_OUTPUT_ROOT is also the build/run dir, and a caseroot may sit inside
    the input dir. Each is then handled once, through its outermost listed
    ancestor. Paths that reach the same dir through a symlink (e.g. a caseroot
    under ~/sch -> scratch) are not caught by comparing them, so a path is
    also skipped if it is gone by the time it would be moved.
    """

    def __init__(self, paths, override):
        self._paths = []
        for p in paths:
            p = Path(os.path.normpath(Path(p).expanduser().absolute()))
            if p not in self._paths:
                self._paths.append(p)
        self._preexisting = {p for p in self._paths if p.exists()}
        self._moved = {}
        if not override:
            return
        # Outermost first, so a nested path goes aside with its ancestor.
        for p in sorted(self._paths, key=lambda q: len(q.parts)):
            if p not in self._preexisting or self._inside_moved(p):
                continue
            if not p.exists():  # already moved aside under another name
                continue
            backup = p.with_name(f"{p.name}.previous-{uuid.uuid4().hex[:8]}")
            print(f"Moving previous case files aside: {p}")
            try:
                p.rename(backup)
            except BaseException:
                self._restore()
                raise
            self._moved[p] = backup

    def _inside_moved(self, p):
        return any(p != m and p.is_relative_to(m) for m in self._moved)

    def _restore(self):
        for p, backup in self._moved.items():
            try:
                backup.rename(p)
                print(f"Restored previous case files: {p}")
            except OSError as e:
                print(f"Could not restore {p}; the previous copy is at {backup}: {e}")

    def undo(self):
        # Remove everything first: restoring an ancestor before removing a
        # path nested in it would delete part of the previous case.
        for p in self._paths:
            if p in self._preexisting and p not in self._moved:
                continue
            if p.exists():
                try:
                    shutil.rmtree(p)
                except OSError as e:
                    print(f"Could not remove {p}: {e}")
        self._restore()

    def discard_previous(self):
        for p, backup in self._moved.items():
            print(f"Removing previous case files: {p}")
            try:
                shutil.rmtree(backup)
            except OSError as e:
                print(f"Could not remove {backup}: {e}")
