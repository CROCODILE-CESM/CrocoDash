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

    from CrocoDash.forcing.driver import run_workflow

    run_workflow(config_path="~/croc_input/mycase/extract_forcings/config.json", bc=True, ic=True)

"""

import json
import time
from pathlib import Path

from CrocoDash import case_state
from CrocoDash.forcing.base import ForcingConfigRegistry, WorkflowContext

# Some forcing types depend on another's process step having already run
# (its output isn't in its own inputs/outputs, so there's nothing generic to
# infer this from) -- {flag_name: [flag_names that must run first]}. Kept as
# an explicit, small exception list rather than a generic dependency system,
# since exactly one case of this exists today.
_PROCESS_ORDER_OVERRIDES = {
    "bgcrivernutrients": ["runoff"],
}


def _load(config_path):
    """Load config.json, read case state, and derive common paths."""
    with open(config_path) as f:
        config = json.load(f)
    caseroot = config["caseroot"]
    state = case_state.read(caseroot)
    inputdir = Path(state["inputdir"])
    return config, state, inputdir


def _build_context(config, state, inputdir):
    extract_forcings_dir = inputdir / "extract_forcings"
    return WorkflowContext(
        inputdir=inputdir,
        supergrid_path=state["supergrid_path"],
        vgrid_path=state["vgrid_path"],
        topo_path=state["topo_path"],
        raw_data_dir=extract_forcings_dir / "raw_data",
        regridded_data_dir=extract_forcings_dir / "regridded_data",
        output_path=inputdir / "ocnice",
        config=config,
    )


def run_workflow(config_path, preview=False, **flags):
    """
    Execute the forcing extraction workflow.

    Parameters
    ----------
    config_path : str or Path
        Path to the ``config.json`` written by ``Case.configure_forcings``.
    preview : bool
        Preview task graph without executing.
    **flags : bool
        Which process components to run, e.g. ``ic=True, bc=True, tides=True``.
        Valid names are whatever ``process_components`` keys the forcing
        types present in ``config.json`` declare -- see
        ``ForcingConfigRegistry.resolve_process_targets``.
    """
    config_path = Path(config_path)
    config, state, inputdir = _load(config_path)
    ctx = _build_context(config, state, inputdir)

    targets = ForcingConfigRegistry.resolve_process_targets(config)
    requested = {name for name, enabled in flags.items() if enabled and name in targets}

    for flag_name, deps in _PROCESS_ORDER_OVERRIDES.items():
        if flag_name not in requested:
            continue
        for dep in deps:
            if dep in targets and dep not in requested:
                print(
                    f"[info] '{flag_name}' requires '{dep}' to run first -- "
                    "enabling it automatically"
                )
                requested.add(dep)

    if not requested:
        print("No components selected.")
        return

    # Stable order: anything named as a dependency runs before its dependents.
    order = []
    for flag_name in requested:
        for dep in _PROCESS_ORDER_OVERRIDES.get(flag_name, []):
            if dep in requested and dep not in order:
                order.append(dep)
        if flag_name not in order:
            order.append(flag_name)

    timings = {}
    for flag_name in order:
        configurator, method_name = targets[flag_name]
        _t = time.perf_counter()
        if preview:
            getattr(configurator, method_name)(ctx)
        else:
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
