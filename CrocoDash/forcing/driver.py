"""CrocoDash Forcing Driver

Orchestrates both stages of the forcing workflow for a CrocoDash case:
configuration (``Case.configure_forcings()``, which writes ``config.json``)
and extraction (``Case.process_forcings()``, which reads it back).

Extraction dispatches generically: for every forcing type present in
``config.json``, the matching ``BaseConfigurator`` subclass is deserialized
and asked which process flags it answers to (its ``process_components``
manifest) -- there's no hand-maintained per-type ``if`` branch to update
when a new forcing type is added. The CLI entry point is ``crocodash
process`` (see ``CrocoDash.cli``).

Typical Python usage::

    from CrocoDash.case import Case
    from CrocoDash.forcing.driver import run_workflow

    run_workflow(Case.from_caseroot("/path/to/caseroot"), bc=True, ic=True)

run_workflow() takes the case instead of reading it from disk itself:
case.py imports this module, so importing CrocoDash.case here would be
circular.

A step that declares files (``output_files()``) is recorded in
``extract_forcings/finished_steps.json`` once it has run, with its settings
(``portable_settings()``) and its files. A later run skips the step while its
settings are unchanged and none of its files is missing; ``force=True`` reruns
it. Before a recorded step runs again, ``clean()`` deletes its old files.
"""

import graphlib
import json
import os
import time
from pathlib import Path

from CrocoDash.forcing.base import ForcingConfigRegistry

# <inputdir>/extract_forcings/finished_steps.json:
# {"schema_version": ..., "steps": {flag: {"settings": ..., "files": [...]}}},
# with the files relative to the inputdir. It is a cache: when it can't be
# read, no step counts as finished and every selected step runs.
FINISHED_STEPS_FILENAME = "finished_steps.json"
FINISHED_STEPS_SCHEMA_VERSION = "1.0.0"


def _resolve_process_order_overrides(targets):
    """{flag_name: [flag_names that must run first]}, derived from every
    active configurator's declared `depends_on_outputs` -- so "runoff must
    run before bgcrivernutrients" (etc.) is declared once, on the class that
    needs it (see forcing/bgc.py), instead of hand-maintained here."""
    overrides = {}
    for flag_name, (configurator, _method) in targets.items():
        if not configurator.depends_on_outputs:
            continue
        dep_flags = [
            other_flag
            for other_flag, (other_configurator, _) in targets.items()
            if other_configurator.name.lower() in configurator.depends_on_outputs
        ]
        if dep_flags:
            overrides[flag_name] = dep_flags
    return overrides


def _finished_steps_path(inputdir):
    return Path(inputdir) / "extract_forcings" / FINISHED_STEPS_FILENAME


def read_finished_steps(inputdir):
    """{flag: {"settings": ..., "files": [...]}} for every step recorded as
    finished. {} before the first run, and, with a warning, when the file is
    unreadable or another major schema version wrote it."""
    path = _finished_steps_path(inputdir)
    try:
        with open(path) as f:
            doc = json.load(f)
        steps = doc["steps"]
        readable = doc["schema_version"].split(".")[0] == (
            FINISHED_STEPS_SCHEMA_VERSION.split(".")[0]
        ) and all(isinstance(entry, dict) for entry in steps.values())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, LookupError, TypeError, AttributeError):
        readable = False
    if not readable:
        print(f"[warning] Ignoring {path}: it can't be read, so every step runs.")
        return {}
    return steps


def _write_finished_steps(inputdir, steps):
    path = _finished_steps_path(inputdir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w") as f:
        json.dump(
            {"schema_version": FINISHED_STEPS_SCHEMA_VERSION, "steps": steps},
            f,
            indent=4,
        )
    os.replace(tmp, path)


def portable_settings(configurator, config, inputdir, cesmroot):
    """configurator.step_settings(config) as finished_steps.json records it:
    plain JSON, with the case's inputdir and cesmroot written as $INPUTDIR and
    $CESMROOT, so that the same configuration in another inputdir (a forked or
    bundled case) compares equal."""
    roots = sorted(
        [(str(inputdir), "$INPUTDIR"), (str(cesmroot), "$CESMROOT")],
        key=lambda root: len(root[0]),
        reverse=True,
    )

    def portable(value):
        if isinstance(value, dict):
            return {key: portable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [portable(item) for item in value]
        if isinstance(value, str):
            for root, name in roots:
                if value == root or value.startswith(root + "/"):
                    return name + value[len(root) :]
        return value

    settings = json.loads(json.dumps(configurator.step_settings(config), default=str))
    return portable(settings)


def _is_finished(configurator, flag_name, ctx, entry, settings):
    """Recorded with the current settings, and every file it declares is
    there. A step that declares no files never counts as finished."""
    return (
        entry is not None
        and entry.get("settings") == settings
        and bool(configurator.output_files(ctx).get(flag_name))
        and not configurator.missing_output_files(ctx, flag_name)
    )


def _relative(paths, inputdir):
    return [Path(path).relative_to(inputdir).as_posix() for path in paths]


def clean(ctx, configurator, step, entry):
    """Delete what an earlier run of *step* made, before it runs again: the
    files its finished_steps.json *entry* lists and the files it declares now.

    The engines skip a final file they find already written (that is how a
    crashed run resumes), so without this a rerun would keep the old files.
    Only files inside the inputdir are deleted.
    """
    inputdir = Path(os.path.normpath(ctx.inputdir))
    paths = [inputdir / name for name in entry.get("files", [])]
    paths += configurator.get_output_filepaths(ctx, step)
    removed = []
    for path in sorted({Path(os.path.normpath(path)) for path in paths}):
        if path.is_relative_to(inputdir) and path.is_file():
            path.unlink()
            removed.append(path)
    if removed:
        print(f"[clean] {step}: removed {len(removed)} file(s) from an earlier run")


def run_workflow(case, *, preview=False, force=False, **flags):
    """
    Execute the forcing extraction workflow.

    Parameters
    ----------
    case : CrocoDash.case.Case
        The case to process, created in this session or read back with
        ``Case.from_caseroot``. Its ``workflow_context()`` carries the
        ``config.json`` that ``Case.configure_forcings`` wrote.
    preview : bool
        Print each selected step, whether it is finished or would run, and
        whether its files are present, without running anything.
    force : bool
        Rerun the requested steps even when they are finished. Steps that only
        run because a requested step depends on them are still skipped when
        finished.
    **flags : bool
        Which process components to run, e.g. ``ic=True, bc=True, tides=True``.
        Valid names are whatever ``process_components`` keys the forcing
        types present in ``config.json`` declare -- see
        ``ForcingConfigRegistry.resolve_process_targets``.
    """
    ctx = case.workflow_context()

    targets = ForcingConfigRegistry.resolve_process_targets(ctx.config)
    requested = {name for name, enabled in flags.items() if enabled and name in targets}
    forced = set(requested) if force else set()

    order_overrides = _resolve_process_order_overrides(targets)

    # Auto-enable dependencies transitively: requesting a flag also requests
    # everything it depends on, however many levels deep.
    frontier = list(requested)
    while frontier:
        flag_name = frontier.pop()
        for dep in order_overrides.get(flag_name, []):
            if dep not in requested:
                print(
                    f"[info] '{flag_name}' requires '{dep}' to run first -- "
                    "enabling it automatically"
                )
                requested.add(dep)
                frontier.append(dep)

    if not requested:
        print("No components selected.")
        return

    # order_overrides is already {node: predecessors}, so hand it straight to
    # TopologicalSorter for a stable order instead of looping over `requested`
    # (a set, whose iteration order isn't meaningful). Every requested flag is
    # passed as a key -- including ones with no declared deps -- so
    # TopologicalSorter doesn't drop flags that never appear in
    # order_overrides.
    graph = {flag_name: order_overrides.get(flag_name, []) for flag_name in requested}
    try:
        order = list(graphlib.TopologicalSorter(graph).static_order())
    except graphlib.CycleError as exc:
        raise RuntimeError(
            f"Circular process-order dependency among forcing components: {exc.args[1]}"
        ) from exc

    finished_steps = read_finished_steps(ctx.inputdir)
    settings, finished = {}, set()
    for flag_name in order:
        configurator, _ = targets[flag_name]
        settings[flag_name] = portable_settings(
            configurator, ctx.config, ctx.inputdir, case.cesmroot
        )
        entry = finished_steps.get(flag_name)
        if flag_name not in forced and _is_finished(
            configurator, flag_name, ctx, entry, settings[flag_name]
        ):
            finished.add(flag_name)

    if preview:
        for flag_name in order:
            configurator, _ = targets[flag_name]
            state = "finished" if flag_name in finished else "would run"
            print(f"[preview] {flag_name}: {state}")
            for path in configurator.get_output_filepaths(ctx, flag_name):
                print(f"    present  {path.relative_to(ctx.inputdir)}")
            for path in configurator.missing_output_files(ctx, flag_name):
                print(f"    missing  {path.relative_to(ctx.inputdir)}")
        return {}

    timings = {}
    for flag_name in order:
        configurator, method_name = targets[flag_name]
        if flag_name in finished:
            print(f"[skip] {flag_name}: finished (force=True / --force reruns it)")
            continue
        entry = finished_steps.pop(flag_name, None)
        if entry is not None:
            clean(ctx, configurator, flag_name, entry)
            _write_finished_steps(ctx.inputdir, finished_steps)

        _t = time.perf_counter()
        getattr(configurator, method_name)(ctx)
        timings[flag_name] = time.perf_counter() - _t

        if configurator.output_files(ctx).get(flag_name):
            missing = configurator.missing_output_files(ctx, flag_name)
            if missing:
                print(
                    f"[warning] {flag_name} didn't write "
                    + ", ".join(_relative(missing, ctx.inputdir))
                    + "; the next run repeats it"
                )
            finished_steps[flag_name] = {
                "settings": settings[flag_name],
                "files": _relative(
                    configurator.get_output_filepaths(ctx, flag_name), ctx.inputdir
                ),
            }
            _write_finished_steps(ctx.inputdir, finished_steps)

    if timings:
        parts = [f"{k}: {v:.1f}s" for k, v in timings.items()]
        parts.append(f"total: {sum(timings.values()):.1f}s")
        print("[timing] " + "  ".join(parts))

    return timings


def resolve_components(args, config):
    """Resolve which components to run based on CLI args and config availability."""
    available_flags = ForcingConfigRegistry.available_process_flags(config)

    components = {
        k: v
        for k, v in vars(args).items()
        if isinstance(v, bool) and k not in {"all", "preview", "force"}
    }
    skip = {s.lower() for s in args.skip}

    for name in components:
        requested = args.all or getattr(args, name)
        exists = name in available_flags
        should = requested and exists and name not in skip

        if requested and not exists:
            print(f"[skip] '{name}' requested but not in config")
        elif requested and name in skip:
            print(f"[skip] '{name}' skipped via --skip")

        setattr(args, name, should)

    return args
