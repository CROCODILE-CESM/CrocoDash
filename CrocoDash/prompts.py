"""Prompts that walk a user through a case's forcings: ``crocodash create`` and
``crocodash configure`` on a terminal, and ``case.configure_forcings(ask=True)``.

The questions come from what each forcing configurator declares (its inputs and
their ParamSpecs), so a new configurator or input is asked about without any
change here.
"""

import json
import textwrap
from pathlib import Path

from CrocoDash.forcing.base import ForcingConfigRegistry
from CrocoDash.raw_data_access.registry import ProductRegistry

# configure_forcings()'s function_overrides, one ParamSpec per key.
_OVERRIDES = "function_overrides."


def ask_string(prompt, default=""):
    """The answer typed at prompt, or default for an empty one. The end of
    input (EOFError) is left to the caller."""
    return input(prompt).strip() or default


def read_yaml(text):
    """text read as YAML, with dates as strings: an unquoted 2020-01-01 reads
    as a date, but configure_forcings() takes date strings."""
    import yaml

    return json.loads(json.dumps(yaml.safe_load(text), default=str))


def ask_value(label, default, why_not_default=None, as_yaml=True):
    """The value typed for label, or default for an empty answer, unless
    why_not_default says why it can't be used: then Enter asks again. With
    as_yaml, the answer is read as YAML, so lists and numbers work."""
    if default is None or isinstance(default, str):
        shown = default or ""
    else:
        shown = json.dumps(default, default=str)
    note = f" ({why_not_default})" if why_not_default else ""
    while True:
        answer = ask_string(f"{label} [{shown}]{note}: ")
        if answer:
            return read_yaml(answer) if as_yaml else answer
        if not why_not_default:
            return default


def _needs_user_input(configurator_cls):
    """Whether configurator_cls takes an input the user has to give (one
    without a default that the Case or configure_forcings() doesn't fill in).
    An allowed configurator that doesn't is active whenever the compset allows
    it."""
    _, required = ForcingConfigRegistry.get_ctor_signature(configurator_cls)
    derived = {param.name for param in configurator_cls.input_params if param.derived}
    return any(not (arg.startswith("case_") or arg in derived) for arg in required)


def _specs(configurator_cls, values):
    """configurator_cls's ParamSpecs, as if the compset required it, given the
    answers so far: conditions' function_overrides depend on its product."""
    inputs = {name: value for name, value in values.items() if "." not in name}
    inputs["function_args"] = {
        name.removeprefix(_OVERRIDES): value
        for name, value in values.items()
        if name.startswith(_OVERRIDES)
    }
    return configurator_cls.param_specs(True, inputs)


def _in_choices(value, choices):
    allowed = {str(choice).lower() for choice in choices}
    return all(
        str(item).lower() in allowed
        for item in (value if isinstance(value, list) else [value])
    )


def _ask_spec(spec, value):
    note = f"{spec.configurator}{' (required)' if spec.required else ''}"
    if spec.comment:
        note += f": {spec.comment.rstrip('.')}"
    if spec.choices:
        note += f". Choices: {', '.join(map(str, spec.choices))}"
    if spec.is_path and isinstance(value, str) and not Path(value).exists():
        note += ". Not found on this machine"
    print("\n".join(f"# {line}" for line in textwrap.wrap(note, 76)))
    while True:
        why_not = "required" if spec.required and value is None else None
        answer = ask_value(spec.name, value, why_not)
        if answer is None or not spec.choices or _in_choices(answer, spec.choices):
            return answer
        print(f"  {answer} isn't one of the choices.")


def _ask_optional(optional, chosen):
    """The optional configurators the user picks, offering chosen."""
    by_name = {cls.name.lower(): cls for cls in optional}
    offered = ",".join(cls.name for cls in chosen) or "none"
    while True:
        answer = ask_string(f"Add which optional forcings? [{offered}]: ", offered)
        picked = [name.strip().lower() for name in answer.replace(",", " ").split()]
        picked = [name for name in picked if name != "none"]
        unknown = [name for name in picked if name not in by_name]
        if not unknown:
            return [cls for cls in optional if cls.name.lower() in picked]
        print(f"  Not an optional forcing here: {', '.join(unknown)}")


def ask_forcings(compset, current=None):
    """Walk through compset's forcings and return configure_forcings()
    arguments.

    Lists the forcings that are on (the compset requires them, or allows them
    and they need no input) and the optional ones, asks which optional ones to
    add, then asks each input of the chosen set. Each question offers
    ``current``'s value (a case's forcing_args()), or the default: Enter keeps
    it, and a required input without one has to be given. The end of input
    (Ctrl-D, or a script's last line) keeps the offered values of the rest.
    """
    ProductRegistry.load()
    values = {
        name: value
        for name, value in (current or {}).items()
        if name != "function_overrides"
    }
    for name, value in ((current or {}).get("function_overrides") or {}).items():
        values[_OVERRIDES + name] = value

    on, optional = [], []
    for cls in ForcingConfigRegistry.registered_types:
        if cls.is_required(compset):
            on.append(cls)
        elif cls.validate_compset_compatibility(compset):
            (optional if _needs_user_input(cls) else on).append(cls)
    # The ones with inputs that have no default (date_range) first.
    on.sort(key=lambda cls: not any(spec.required for spec in _specs(cls, values)))

    def names(classes):
        return ", ".join(cls.name for cls in classes) or "none"

    print(f"\nForcings for {compset}\n  on: {names(on)}\n  optional: {names(optional)}")
    # The optional ones current has every required input of.
    chosen = [
        cls
        for cls in optional
        if all(
            values.get(spec.name) is not None
            for spec in _specs(cls, values)
            if spec.required
        )
    ]
    try:
        if optional:
            chosen = _ask_optional(optional, chosen)
        print("\nInputs (Enter keeps the value in brackets; answers are read as YAML):")
        asked = set()
        for cls in on + chosen:
            # One at a time, since the specs depend on the answers so far:
            # conditions' function_overrides follow its product and function.
            while spec := next(
                (spec for spec in _specs(cls, values) if spec.name not in asked), None
            ):
                values[spec.name] = _ask_spec(spec, values.get(spec.name, spec.default))
                asked.add(spec.name)
    except EOFError:
        print("\nEnd of input: the rest keep the values offered.")

    specs = [spec for cls in on + chosen for spec in _specs(cls, values)]
    missing = sorted(
        {spec.name for spec in specs if spec.required and values.get(spec.name) is None}
    )
    if missing:
        raise ValueError(f"The forcings need {', '.join(missing)}.")
    # Only the active configurators' inputs: a dropped optional forcing's
    # would otherwise turn it back on.
    kept = {spec.name for spec in specs}
    args = {
        name: value
        for name, value in values.items()
        if name in kept and not name.startswith(_OVERRIDES)
    }
    overrides = {
        name.removeprefix(_OVERRIDES): value
        for name, value in values.items()
        if name in kept and name.startswith(_OVERRIDES)
    }
    if overrides:
        args["function_overrides"] = overrides
    return args
