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

Each step that finishes with every file it declares (``output_files()``) is
recorded in ``extract_forcings/process_record.json`` against its
``process_fingerprint()``. A later run skips a step whose fingerprint is
unchanged and whose files are all still there; ``force=True`` reruns it.

Typical Python usage::

    from CrocoDash.forcing.driver import run_workflow

    run_workflow(config_path="~/croc_input/mycase/extract_forcings/config.json", bc=True, ic=True)

"""

import graphlib
import json
import os
import time
from pathlib import Path

from CrocoDash.forcing.base import ForcingConfigRegistry, ReadCrocoDashCase

RECORD_FILENAME = "process_record.json"


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


def _record_path(inputdir):
    return Path(inputdir) / "extract_forcings" / RECORD_FILENAME


def read_record(inputdir):
    """{flag: {"fingerprint": ..., "files": [...]}} for every process step
    recorded as done ({} before the first run, or after override=True)."""
    try:
        with open(_record_path(inputdir)) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _write_record(inputdir, record):
    path = _record_path(inputdir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w") as f:
        json.dump(record, f, indent=4)
    os.replace(tmp, path)


def _fingerprint(configurator, config):
    # Compare like with like: the recorded fingerprint was read back from JSON.
    return json.loads(json.dumps(configurator.process_fingerprint(config), default=str))


def is_done(configurator, flag_name, ctx, record):
    """True when flag_name was recorded as done for the configuration in
    ctx.config and every file it declares is still there."""
    entry = record.get(flag_name)
    return (
        entry is not None
        and entry.get("fingerprint") == _fingerprint(configurator, ctx.config)
        and not configurator.missing_output_files(ctx, flag_name)
    )


def _relative(paths, inputdir):
    return [Path(path).relative_to(inputdir).as_posix() for path in paths]


def summarize_paths(paths, limit=5):
    if len(paths) <= limit:
        return ", ".join(paths)
    return ", ".join(paths[:limit]) + f", ... ({len(paths)} files)"


def run_workflow(config_path, preview=False, force=False, **flags):
    """
    Execute the forcing extraction workflow.

    Parameters
    ----------
    config_path : str or Path
        Path to the ``config.json`` written by ``Case.configure_forcings``.
    preview : bool
        Print what would run or be skipped, and each step's files, without
        running anything.
    force : bool
        Rerun the selected steps even when they are recorded as done.
    **flags : bool
        Which process components to run, e.g. ``ic=True, bc=True, tides=True``.
        Valid names are whatever ``process_components`` keys the forcing
        types present in ``config.json`` declare -- see
        ``ForcingConfigRegistry.resolve_process_targets``.
    """
    with open(config_path) as f:
        config = json.load(f)
    case = ReadCrocoDashCase(config["caseroot"])
    ctx = case.workflow_context(config)
    inputdir = ctx.inputdir

    targets = ForcingConfigRegistry.resolve_process_targets(config)
    requested = {name for name, enabled in flags.items() if enabled and name in targets}

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

    record = read_record(inputdir)
    done = {
        flag_name
        for flag_name in order
        if not force and is_done(targets[flag_name][0], flag_name, ctx, record)
    }

    if preview:
        for flag_name in order:
            configurator, _ = targets[flag_name]
            verdict = "skip, already done" if flag_name in done else "run"
            print(f"[preview] {flag_name}: {verdict}")
            present = configurator.get_output_filepaths(ctx, flag_name)
            missing = configurator.missing_output_files(ctx, flag_name)
            for path in _relative(present, inputdir):
                print(f"    present  {path}")
            for path in _relative(missing, inputdir):
                print(f"    missing  {path}")
        return {}

    timings = {}
    for flag_name in order:
        configurator, method_name = targets[flag_name]
        if flag_name in done:
            n_files = len(configurator.get_output_filepaths(ctx, flag_name))
            print(
                f"[skip] {flag_name}: already done, {n_files} file(s) present "
                "(force=True / --force reruns it)"
            )
            continue
        _t = time.perf_counter()
        getattr(configurator, method_name)(ctx)
        timings[flag_name] = time.perf_counter() - _t

        missing = configurator.missing_output_files(ctx, flag_name)
        if missing:
            # Not recorded as done, so the next run repeats it.
            print(
                f"[incomplete] {flag_name} didn't write "
                f"{summarize_paths(_relative(missing, inputdir))}"
            )
            record.pop(flag_name, None)
        else:
            written = _relative(
                configurator.get_output_filepaths(ctx, flag_name), inputdir
            )
            if written:
                print(f"[{flag_name}] wrote {summarize_paths(written)}")
            record[flag_name] = {
                "fingerprint": _fingerprint(configurator, config),
                "files": written,
            }
        # After every step, so a later failure keeps the steps already done.
        _write_record(inputdir, record)

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
