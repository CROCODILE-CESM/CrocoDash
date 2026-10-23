"""StreamYears writes visualCaseGen's stream year plan into the case.

The planning itself (stream names, coverage, file lists) is tested in
visualCaseGen against the real CDEPS stream definitions, so it is mocked here.
"""

from types import SimpleNamespace
from unittest.mock import patch

from visualCaseGen import user_nl_blocks

from CrocoDash.forcing.atm import StreamYearConfigurator
from CrocoDash.forcing.base import USER_NL_TAG


def test_writes_the_plan_into_crocodash_block(tmp_path):
    """A configured component gets one line per setting in its streams file,
    in the block the next configure_forcings() replaces; a skipped one is left
    at the CDEPS defaults."""
    plans = {
        "datm": {
            "status": "configured",
            "mode": "CORE_IAF_JRA",
            "streams": {
                "CORE_IAF_JRA.PREC": {
                    "year_first": 2014,
                    "year_last": 2016,
                    "year_align": 2014,
                    "datafiles": ["a.nc", "b.nc"],
                }
            },
        },
        "drof": {"status": "skipped", "reason": "no streams defined for IAF_JRA"},
    }
    modes = {"DATM_MODE": "CORE_IAF_JRA", "DROF_MODE": "IAF_JRA"}
    configurator = StreamYearConfigurator(
        case_cesmroot="/cesm", start_date="20150601", end_date="20150701"
    )
    configurator.registry = SimpleNamespace(
        case=SimpleNamespace(
            _cime_case=SimpleNamespace(get_value=modes.get), caseroot=tmp_path, ninst=1
        )
    )
    with patch(
        "CrocoDash.forcing.atm.plan_stream_years",
        side_effect=lambda cesmroot, component, *args, **kwargs: plans[component],
    ) as plan:
        configurator.configure()

    assert plan.call_args.kwargs == {"padding": 1, "narrow": True}
    assert configurator.get_output_param("datm_streams") == plans["datm"]
    streams = tmp_path / "user_nl_datm_streams"
    assert "CORE_IAF_JRA.PREC:year_align = 2014\n" in streams.read_text()
    assert "CORE_IAF_JRA.PREC:datafiles = a.nc,b.nc\n" in streams.read_text()
    assert not (tmp_path / "user_nl_drof_streams").exists()

    user_nl_blocks.strip(tmp_path, USER_NL_TAG)
    assert "CORE_IAF_JRA" not in streams.read_text()
