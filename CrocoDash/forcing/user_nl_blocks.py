"""CrocoDash-managed blocks in a case's ``user_nl_*`` files.

``Case.configure_forcings()`` may be called again on the same case (a notebook
cell rerun, or a new date range), so the user_nl entries it writes go inside
marked blocks, one per configurator and file::

    ! >>> CrocoDash configure_forcings: conditions [sha:1a2b3c4d] (rewritten ...)
    ...
    ! <<< CrocoDash configure_forcings: conditions

Every call first removes all such blocks (``strip``), then writes its own
(``write``), so the files end up as if only the latest call had happened.
Lines outside the blocks are left alone: what case creation wrote (INPUTDIR,
the WW3 time steps, CICE's ndtd) and whatever the user added.

A variable the user sets outside the blocks takes precedence: ``write`` leaves
it out of CrocoDash's block. Otherwise user_nl_mom would list it twice, which
stops the MOM6 build, and CICE, WW3 and CDEPS would take whichever line comes
last.

The marker lines are ``!`` comments, which MOM_interface's user_nl parser,
CIME's namelist parser and CDEPS's stream-mod parser all skip.
"""

import hashlib
import re
from pathlib import Path

from ProConPy.config_var import cvars
from visualCaseGen.custom_widget_types.case_tools import append_user_nl

_BEGIN = "! >>> CrocoDash configure_forcings: "
_END = "! <<< CrocoDash configure_forcings: "
_NOTE = "(rewritten on every call; set your own values outside this block)"
_BEGIN_RE = re.compile(re.escape(_BEGIN) + r"(\S+) \[sha:([0-9a-f]+)\]")


def _sha(body):
    return hashlib.sha1(body.encode()).hexdigest()[:8]


def _files(caseroot, model, ninst):
    """The user_nl files append_user_nl writes for this model."""
    if ninst is None or ninst == 1:
        return [caseroot / f"user_nl_{model}"]
    return [
        caseroot / f"user_nl_{model}_{str(i).zfill(4)}" for i in range(1, ninst + 1)
    ]


def _parse(lines, path):
    """[(owner, sha, begin, end)] line indices of the blocks in ``lines``."""
    blocks = []
    i = 0
    while i < len(lines):
        match = _BEGIN_RE.match(lines[i])
        if match:
            owner, sha = match.groups()
            end_line = f"{_END}{owner}"
            end = next(
                (j for j in range(i + 1, len(lines)) if lines[j].rstrip() == end_line),
                None,
            )
            if end is None:
                raise RuntimeError(
                    f"{path}, line {i + 1}: CrocoDash's '{owner}' block has no "
                    f"'{end_line}' line, so it's unclear where the block ends. "
                    "Restore that line, or delete the block, and call "
                    "configure_forcings() again."
                )
            blocks.append((owner, sha, i, end))
            i = end
        i += 1
    return blocks


def _key(name):
    """A variable name as compared across lines: case-insensitive, and with no
    whitespace, since CDEPS reads "stream : key" and "stream:key" alike."""
    return "".join(name.split()).lower()


def _keys_outside_blocks(lines, path):
    """The (normalized) variables set outside CrocoDash's blocks."""
    inside = set()
    for _, _, begin, end in _parse(lines, path):
        inside.update(range(begin, end + 1))
    keys = set()
    for i, line in enumerate(lines):
        text = line.strip()
        if i in inside or text.startswith("!") or "=" not in text:
            continue
        keys.add(_key(text.split("=", 1)[0]))
    return keys


def _read_lines(path):
    return path.read_text().splitlines(keepends=True) if path.exists() else []


def snapshot(caseroot):
    """The contents of every user_nl file in ``caseroot``, for ``restore``."""
    return {
        path: path.read_text()
        for path in Path(caseroot).glob("user_nl_*")
        if path.is_file()
    }


def restore(caseroot, contents):
    """Put the user_nl files back as ``snapshot`` found them, so that a
    configure_forcings() call that fails leaves them as they were."""
    for path in Path(caseroot).glob("user_nl_*"):
        if path.is_file() and path not in contents:
            path.unlink()
    for path, text in contents.items():
        path.write_text(text)


def strip(caseroot):
    """Remove every CrocoDash block from the user_nl files in ``caseroot``.

    Returns ``[(file name, owner, body lines)]`` for the blocks whose contents
    differ from what CrocoDash wrote, i.e. that were edited by hand, so that
    ``report_edits`` can say what was replaced.
    """
    edited = []
    for path in sorted(Path(caseroot).glob("user_nl_*")):
        if not path.is_file():
            continue
        lines = _read_lines(path)
        blocks = _parse(lines, path)
        if not blocks:
            continue
        keep = [True] * len(lines)
        for owner, sha, begin, end in blocks:
            body = lines[begin + 1 : end]
            if _sha("".join(body)) != sha:
                edited.append((path.name, owner, body))
            keep[begin : end + 1] = [False] * (end + 1 - begin)
            # The blank line write() puts before each block.
            if begin > 0 and keep[begin - 1] and not lines[begin - 1].strip():
                keep[begin - 1] = False
        path.write_text("".join(line for line, k in zip(lines, keep) if k))
    return edited


def write(owner, model, groups):
    """Write ``owner``'s block into user_nl_<model> (each instance's file).

    ``groups`` is ``[(comment or None, [(var, val), ...]), ...]``; the block
    holds them as consecutive append_user_nl calls would write them, and the
    log shows them the same way. Variables the file already sets outside the
    blocks are left out (see the module docstring).
    """
    caseroot = Path(cvars["CASEROOT"].value)
    files = _files(caseroot, model, cvars["NINST"].value)

    per_file = []
    for path in files:
        lines = _read_lines(path)
        outside = _keys_outside_blocks(lines, path)
        kept = []
        for comment, pairs in groups:
            pairs = [(var, val) for var, val in pairs if _key(var) not in outside]
            if pairs:
                kept.append((comment, pairs))
        skipped = [
            var for _, pairs in groups for var, _ in pairs if _key(var) in outside
        ]
        per_file.append((path, lines, kept, skipped))

    # The log is what append_user_nl prints for the first instance's entries
    # (it repeats them for every instance, as when it writes them itself).
    for i, (comment, pairs) in enumerate(per_file[0][2]):
        append_user_nl(model, pairs, do_exec=False, comment=comment, log_title=i == 0)
    for path, _, _, skipped in per_file:
        for var in skipped:
            print(
                f"  ! {var}: set outside CrocoDash's block in {path.name}; "
                "that value is kept"
            )

    for path, lines, kept, _ in per_file:
        if not kept:
            continue
        body = "".join(
            (f"\n! {comment}\n" if comment else "")
            + "".join(f"{var} = {val}\n" for var, val in pairs)
            for comment, pairs in kept
        )
        separator = "" if not lines or lines[-1].endswith("\n") else "\n"
        with open(path, "a") as f:
            f.write(
                f"{separator}\n{_BEGIN}{owner} [sha:{_sha(body)}] {_NOTE}\n"
                f"{body}{_END}{owner}\n"
            )


def report_edits(caseroot, edited):
    """Warn about the hand edits ``strip`` found, once the blocks have been
    rewritten: the lines each edited block lost, and those it got back."""
    for name, owner, body in edited:
        path = Path(caseroot) / name
        lines = _read_lines(path)
        new = [
            line.strip()
            for block_owner, _, begin, end in _parse(lines, path)
            if block_owner == owner
            for line in lines[begin + 1 : end]
            if line.strip()
        ]
        old = [line.strip() for line in body if line.strip()]
        discarded = [line for line in old if line not in new]
        restored = [line for line in new if line not in old]
        if not discarded and not restored:
            continue
        print(
            f"WARNING: {name} was edited inside CrocoDash's '{owner}' block, "
            "which configure_forcings() rewrites on every call."
        )
        for label, changed in (("Discarded", discarded), ("Written back", restored)):
            if changed:
                print(f"  {label}:")
                for line in changed:
                    print(f"    {line}")
        print(
            "  Set your own values outside the '! >>> CrocoDash' blocks instead: "
            "those are kept, and take precedence over CrocoDash's."
        )
