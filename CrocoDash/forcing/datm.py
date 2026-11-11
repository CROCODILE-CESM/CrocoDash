"""The data atmosphere: a JRA or CORE2 IAF DATM reads the run's own years of
its forcing. Runoff does the same for a JRA or GLOFAS DROF (see stream_years)."""

from pathlib import Path

import pandas as pd

from CrocoDash.forcing.base import *

# STOP_OPTION units as pandas DateOffset keywords.
_STOP_UNITS = {"ndays": "days", "nmonths": "months", "nyears": "years"}


def _default_years(srcroot, component, compset):
    """The (start, end) years <COMP>_YR_START/_END default to for this
    compset: for an interannual stream, the years its data covers. None when
    this CESM's CDEPS doesn't define them."""
    # CIME is on sys.path once a Case exists.
    from CIME.XML.component import Component

    config = Path(srcroot) / "components" / "cdeps" / component / "cime_config"
    comp = Component(str(config / "config_component.xml"), component[1:].upper())
    years = []
    for var in ("START", "END"):
        node = comp.get_optional_child("entry", {"id": f"{component.upper()}_YR_{var}"})
        if node is None:
            return None
        # How create_newcase picks a compset's default.
        years.append(int(comp.get_default_value(node, {"compset": compset})))
    return tuple(years)


def stream_years(caseroot, component):
    """The <COMP>_YR_ALIGN/_START/_END that make ``component`` ("datm" or
    "drof") read the run's own years of its interannual streams (JRA, CORE2
    IAF, GLOFAS), worked out from the case's xml. They take one data year
    either side of the run, for the time interpolation at its ends, inside the
    years the data covers. None when the component's streams aren't
    interannual.

    CDEPS then lists only those years' files. At its defaults (align 1, data
    from 1958) model year 2020 would read JRA's 1997.
    """
    comp = component.upper()
    compset = xmlquery("COMPSET", caseroot=caseroot)
    if f"_{comp}%" not in compset:
        return None
    coverage = _default_years(
        xmlquery("SRCROOT", caseroot=caseroot), component, compset
    )
    if coverage is None or coverage[0] >= coverage[1]:
        return None
    data_first, data_last = coverage

    start = pd.Timestamp(xmlquery("RUN_STARTDATE", caseroot=caseroot))
    unit = _STOP_UNITS[xmlquery("STOP_OPTION", caseroot=caseroot)]
    end = start + pd.DateOffset(**{unit: int(xmlquery("STOP_N", caseroot=caseroot))})
    run_first, run_last = start.year, (end - pd.Timedelta(days=1)).year
    if run_first < data_first or run_last > data_last:
        raise ValueError(
            f"The run's {run_first}-{run_last} fall outside the "
            f"{data_first}-{data_last} that {comp}'s data covers."
        )
    first, last = max(data_first, run_first - 1), min(data_last, run_last + 1)
    return {
        f"{comp}_YR_ALIGN": first,
        f"{comp}_YR_START": first,
        f"{comp}_YR_END": last,
    }


@register
class DATMConfigurator(BaseConfigurator):
    name = "DATM"
    # The DATM modes whose streams read DATM_YR_* (CDEPS's own compset patterns).
    required_for_compsets = [
        "DATM%JRA_",
        "DATM%JRA-1p4-2018",
        "DATM%JRA-1p5-2023",
        "DATM%IAF",
    ]
    allowed_compsets = ["DATM"]

    input_params = []
    output_params = [
        XMLConfigParam("DATM_YR_ALIGN", comment="Model year that reads DATM_YR_START"),
        XMLConfigParam("DATM_YR_START", comment="First year of DATM data read"),
        XMLConfigParam("DATM_YR_END", comment="Last year of DATM data read"),
    ]

    def __init__(self):
        super().__init__()

    def configure(self):
        years = stream_years(self.registry.case.caseroot, "datm")
        if years is None:
            raise ValueError(
                "This case's DATM streams don't read DATM_YR_*. Aligning them needs "
                "a CDEPS whose JRA and CORE2 IAF streams do."
            )
        for name, year in years.items():
            self.set_output_param(name, year)
        super().configure()
