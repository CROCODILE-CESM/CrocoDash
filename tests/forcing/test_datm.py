from CrocoDash.forcing import datm


def test_stream_years_cover_the_run_with_a_year_either_side(monkeypatch):
    """At CDEPS's defaults a JRA case starting in 2020 read 1997. The extra
    year either side, for the time interpolation, stays inside the data: a
    2023 run with JRA 1.5 (1958-2023) doesn't ask for 2024."""
    xml = {
        "COMPSET": "2000_DATM%JRA-1p5-2023_SLND_SICE_MOM6%REGIONAL_DROF%GLOFAS_SGLC_SWAV",
        "SRCROOT": "/cesm",
        "RUN_STARTDATE": "2023-01-01",
        "STOP_OPTION": "ndays",
        "STOP_N": "365",
    }
    coverage = {"datm": (1958, 2023), "drof": (1979, 2024)}
    monkeypatch.setattr(datm, "xmlquery", lambda var, caseroot: xml[var])
    monkeypatch.setattr(
        datm, "_default_years", lambda root, comp, lname: coverage[comp]
    )

    assert datm.stream_years("/x", "datm") == {
        "DATM_YR_ALIGN": 2022,
        "DATM_YR_START": 2022,
        "DATM_YR_END": 2023,
    }
    assert datm.stream_years("/x", "drof")["DROF_YR_END"] == 2024

    # A climatology (NYF, RYF) has nothing to align.
    coverage["datm"] = (2004, 2004)
    assert datm.stream_years("/x", "datm") is None
