from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from CrocoDash.forcing import utils


def test_stream_years_cover_the_run_with_a_year_either_side():
    """At CDEPS's defaults a JRA case starting in 2020 read 1997. The extra
    year either side, for the time interpolation, stays inside the data: a
    2023 run with JRA 1.5 (1958-2023) doesn't ask for 2024."""
    coverage = {"datm": (1958, 2023), "drof": (1979, 2024)}
    case = SimpleNamespace(
        caseroot="/x",
        is_non_local=False,
        cesmroot="/cesm",
        compset_lname="2000_DATM%JRA-1p5-2023_SLND_SICE_MOM6%REGIONAL_DROF%GLOFAS_SGLC_SWAV",
        date_range=pd.to_datetime(["2023-01-01", "2024-01-01"]),
    )
    changes = {}
    with patch.object(
        utils, "_default_years", lambda cesmroot, comp, lname: coverage[comp]
    ), patch.object(
        utils, "xmlchange", lambda var, val, **kw: changes.update({var: val})
    ):
        utils.set_stream_years(case, "datm")
        utils.set_stream_years(case, "drof")
        assert changes == {
            "DATM_YR_ALIGN": 2022,
            "DATM_YR_START": 2022,
            "DATM_YR_END": 2023,
            "DROF_YR_ALIGN": 2022,
            "DROF_YR_START": 2022,
            "DROF_YR_END": 2024,
        }

        # A climatology (NYF, RYF) keeps its defaults.
        coverage["datm"] = (2004, 2004)
        changes.clear()
        assert utils.set_stream_years(case, "datm") == {}
        assert changes == {}
