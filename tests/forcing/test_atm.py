"""Tests for DATM/DROF stream year alignment.

These read the real CDEPS stream definitions out of a CESM checkout, so they
are gated on GLADE. The datestamp assertions are deliberately exact: they
double as a guard on the private CDEPS helpers (`_sub_paths`,
`_resolve_values`, `_get_stream_first_and_last_dates`) that
`cdeps_streams` calls, so a CESM bump that changes them fails here rather
than silently emitting file paths that do not exist.
"""

import os
from unittest.mock import patch

import pytest

from CrocoDash.forcing import cdeps_streams
from CrocoDash.forcing.atm import StreamYearConfigurator

INPUTDATA = "/glade/campaign/cesm/cesmdata/inputdata"


class FakeCimeCase:
    """Stands in for a CIME Case: only xml lookup and $-expansion are used."""

    def __init__(self, **values):
        self._values = {"DIN_LOC_ROOT": INPUTDATA, **values}

    def get_value(self, name):
        return self._values.get(name)

    def get_resolved_value(self, value):
        return value.replace("$DIN_LOC_ROOT", INPUTDATA)


class FakeRegistry:
    def __init__(self, cime_case):
        self.case = type("FakeCase", (), {"_cime_case": cime_case})()


def build(cesmroot, start, end, cime_case, **kwargs):
    configurator = StreamYearConfigurator(
        case_cesmroot=cesmroot, start_date=start, end_date=end, **kwargs
    )
    configurator.registry = FakeRegistry(cime_case)
    return configurator


@pytest.fixture
def cesmroot(skip_if_not_glade, get_cesm_root_path):
    if not os.path.isdir(
        os.path.join(get_cesm_root_path, "components", "cdeps", "cime_config")
    ):
        pytest.skip("CESM checkout has no CDEPS component")
    return get_cesm_root_path


@pytest.mark.parametrize(
    "component,mode,expected_first,n_streams",
    [
        ("datm", "CORE_IAF_JRA", "CORE_IAF_JRA.PREC", 8),
        ("datm", "CORE_IAF_JRA_1p5_2023", "CORE_IAF_JRA_1p5_2023.GCGCS.PREC", 8),
        ("datm", "CORE2_NYF", "CORE2_NYF.GISS", 3),
        ("drof", "IAF_JRA", "rof.iaf_jra", 1),
    ],
)
def test_stream_names(cesmroot, component, mode, expected_first, n_streams):
    """Stream names come from CIME's regex-matched lookup, not a prefix rule.

    CORE_IAF_JRA_1p5_2023 and IAF_JRA both name their streams differently from
    their mode, so prefixing would silently return nothing.
    """
    names = cdeps_streams.stream_names(cesmroot, component, mode)
    assert len(names) == n_streams
    assert names[0] == expected_first


def test_multi_datestamp_files_resolve_per_year(cesmroot):
    """JRA v1.5 splits its years across four <file> entries, each with its own
    datestamp. Each year must pick up the stamp of the entry covering it."""
    paths = cdeps_streams.datafiles(
        cesmroot,
        "datm",
        "CORE_IAF_JRA_1p5_2023.GCGCS.PREC",
        2020,
        2022,
        FakeCimeCase(),
    )
    assert [os.path.basename(p) for p in paths] == [
        "JRA.v1.5.prec.TL319.2020.210504.nc",
        "JRA.v1.5.prec.TL319.2021.220505.nc",
        "JRA.v1.5.prec.TL319.2022.230718.nc",
    ]


@pytest.mark.parametrize(
    "component,mode,first,last",
    [
        ("datm", "CORE_IAF_JRA", 1958, 2016),
        ("datm", "CORE2_NYF", 1, 1),
        ("drof", "IAF_JRA", 1958, 2016),
    ],
)
def test_coverage(cesmroot, component, mode, first, last):
    name = cdeps_streams.stream_names(cesmroot, component, mode)[0]
    assert cdeps_streams.coverage(cesmroot, component, name, FakeCimeCase()) == (
        first,
        last,
    )


@patch("CrocoDash.forcing.atm.append_user_nl")
def test_configures_jra_streams(mock_append, cesmroot):
    """A run inside the covered range gets every stream aligned and narrowed."""
    configurator = build(
        cesmroot,
        "20150601",
        "20150701",
        FakeCimeCase(DATM_MODE="CORE_IAF_JRA", DROF_MODE="IAF_JRA"),
    )
    configurator.configure()

    datm = configurator.get_output_param("datm_streams")
    assert datm["status"] == "configured"
    assert len(datm["streams"]) == 8

    # year_align == year_first is what makes the data year equal the model year.
    for mods in datm["streams"].values():
        assert mods["year_align"] == mods["year_first"]
        assert mods["year_first"] <= 2015 <= mods["year_last"]
        assert all(str(year) in " ".join(mods["datafiles"]) for year in (2014, 2015))

    assert configurator.get_output_param("drof_streams")["status"] == "configured"

    # One append per component, carrying 4 lines per stream.
    written = {call.args[0]: call.args[1] for call in mock_append.call_args_list}
    assert set(written) == {"datm_streams", "drof_streams"}
    assert len(written["datm_streams"]) == 8 * 4
    assert len(written["drof_streams"]) == 1 * 4
    keys = [key for key, _ in written["datm_streams"]]
    assert "CORE_IAF_JRA.PREC:year_align" in keys
    assert "CORE_IAF_JRA.PREC:datafiles" in keys


@patch("CrocoDash.forcing.atm.append_user_nl")
def test_out_of_range_leaves_streams_untouched(mock_append, cesmroot):
    """CORE_IAF_JRA ends in 2016, so a 2020 run cannot be aligned to real years.

    Writing nothing keeps the case building exactly as it does today, rather
    than silently aliasing 2020 onto some other year.
    """
    configurator = build(
        cesmroot,
        "20200101",
        "20200201",
        FakeCimeCase(DATM_MODE="CORE_IAF_JRA"),
    )
    configurator.configure()

    plan = configurator.get_output_param("datm_streams")
    assert plan["status"] == "skipped"
    assert "2020" in plan["reason"] and "1958-2016" in plan["reason"]
    mock_append.assert_not_called()


@patch("CrocoDash.forcing.atm.append_user_nl")
def test_single_year_climatology_is_a_noop(mock_append, cesmroot):
    """NYF is a repeating single year: nothing to align, nothing to narrow."""
    configurator = build(
        cesmroot, "20000101", "20000201", FakeCimeCase(DATM_MODE="CORE2_NYF")
    )
    configurator.configure()

    assert configurator.get_output_param("datm_streams")["status"] == "skipped"
    assert configurator.get_output_param("drof_streams")["status"] == "skipped"
    mock_append.assert_not_called()


@patch("CrocoDash.forcing.atm.append_user_nl")
def test_narrowing_can_be_disabled(mock_append, cesmroot):
    configurator = build(
        cesmroot,
        "20150601",
        "20150701",
        FakeCimeCase(DATM_MODE="CORE_IAF_JRA"),
        narrow_stream_files=False,
    )
    configurator.configure()

    streams = configurator.get_output_param("datm_streams")["streams"]
    assert all("datafiles" not in mods for mods in streams.values())
    keys = [key for key, _ in mock_append.call_args_list[0].args[1]]
    assert not any(key.endswith(":datafiles") for key in keys)


@patch("CrocoDash.forcing.atm.append_user_nl")
def test_padding_widens_the_window(mock_append, cesmroot):
    narrow = build(
        cesmroot,
        "20150601",
        "20150701",
        FakeCimeCase(DATM_MODE="CORE_IAF_JRA"),
        stream_year_padding=0,
    )
    narrow.configure()
    mods = narrow.get_output_param("datm_streams")["streams"]["CORE_IAF_JRA.PREC"]
    # Still one year of lead-in for time interpolation at the run start.
    assert (mods["year_first"], mods["year_last"]) == (2014, 2015)


@patch("CrocoDash.forcing.atm.append_user_nl")
def test_serializes_to_json(mock_append, cesmroot):
    import json

    configurator = build(
        cesmroot,
        "20150601",
        "20150701",
        FakeCimeCase(DATM_MODE="CORE_IAF_JRA", DROF_MODE="IAF_JRA"),
    )
    configurator.configure()

    payload = configurator.serialize()
    json.dumps(payload)  # config.json must round-trip
    restored = StreamYearConfigurator.deserialize(payload)
    assert restored.get_output_param("datm_streams") == configurator.get_output_param(
        "datm_streams"
    )
