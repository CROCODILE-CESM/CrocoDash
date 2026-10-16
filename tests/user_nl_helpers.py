"""Reading user_nl files in tests the way the model's own tools do."""

from pathlib import Path


def keys(text):
    """The variables a user_nl file sets, in order, repeats included."""
    return [
        line.split("=", 1)[0].strip()
        for line in text.splitlines()
        if "=" in line and not line.lstrip().startswith("!")
    ]


def mom_parser(cesmroot):
    """MOM_interface's FType_MOM_params, which reads user_nl_mom at build time
    and exits on any variable listed twice; None if this checkout lacks it.
    It imports CIME, which must be importable already."""
    path = Path(cesmroot) / "components/mom/cime_config/MOM_RPS/FType_MOM_params.py"
    if not path.exists():
        return None
    from CrocoDash.shareable import _load_FType_MOM_params

    return _load_FType_MOM_params(cesmroot).FType_MOM_params
