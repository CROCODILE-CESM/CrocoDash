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
"""

import graphlib
import time

from CrocoDash.forcing.base import ForcingConfigRegistry


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


def run_workflow(case, *, preview=False, **flags):
    """
    Execute the forcing extraction workflow.

    Parameters
    ----------
    case : CrocoDash.case.Case
        The case to process, created in this session or read back with
        ``Case.from_caseroot``. Its ``workflow_context()`` carries the
        ``config.json`` that ``Case.configure_forcings`` wrote.
    preview : bool
        Preview task graph without executing.
    **flags : bool
        Which process components to run, e.g. ``ic=True, bc=True, tides=True``.
        Valid names are whatever ``process_components`` keys the forcing
        types present in ``config.json`` declare -- see
        ``ForcingConfigRegistry.resolve_process_targets``.
    """
    ctx = case.workflow_context(preview=preview)

    targets = ForcingConfigRegistry.resolve_process_targets(ctx.config)
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

    timings = {}
    for flag_name in order:
        configurator, method_name = targets[flag_name]
        _t = time.perf_counter()
        # Each process_*() decides what preview means for it, off ctx.preview.
        getattr(configurator, method_name)(ctx)
        timings[flag_name] = time.perf_counter() - _t

    if timings:
        parts = [f"{k}: {v:.1f}s" for k, v in timings.items()]
        parts.append(f"total: {sum(timings.values()):.1f}s")
        print("[timing] " + "  ".join(parts))

    return timings


def resolve_components(args, config):
    """Resolve which components to run based on CLI args and config availability."""
    available_flags = ForcingConfigRegistry.available_process_flags(config)

    components = {
        k: v for k, v in vars(args).items() if isinstance(v, bool) and k not in {"all"}
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
