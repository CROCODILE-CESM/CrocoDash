"""The forcing walkthrough that `crocodash create` and `crocodash configure`
run on a terminal (CrocoDash.prompts.ask_forcings)."""

from CrocoDash.prompts import ask_forcings

NYF = "1850_DATM%NYF_SLND_SICE_MOM6%REGIONAL_SROF_SGLC_SWAV"


def _type(monkeypatch, answers):
    """Answer each prompt that starts with a key of answers, press Enter at
    the others; or, with answers None, end the input at the first prompt."""

    def typed(prompt):
        if answers is None:
            raise EOFError
        return next((a for label, a in answers.items() if prompt.startswith(label)), "")

    monkeypatch.setattr("builtins.input", typed)


def test_a_chosen_optional_forcing_is_asked_for_and_the_others_are_not(
    monkeypatch, tmp_path
):
    chl = tmp_path / "chl.nc"
    chl.touch()
    _type(
        monkeypatch,
        {
            "Add which optional forcings": "chl",
            "date_range": '["2020-01-01", "2020-01-05"]',
            "chl_processed_filepath": str(chl),
        },
    )

    args = ask_forcings(NYF)

    assert args["date_range"] == ["2020-01-01", "2020-01-05"]
    assert args["chl_processed_filepath"] == str(chl)
    assert "tidal_constituents" not in args


def test_the_end_of_input_keeps_a_case_as_configured(monkeypatch):
    """A short script (or Ctrl-D) reconfigures a case unchanged, keeping the
    optional forcings it has."""
    current = {
        "date_range": ["2020-01-01 00:00:00", "2020-01-05 00:00:00"],
        "boundaries": ["north", "east"],
        "product_name": "GLORYS",
        "function_name": "get_glorys_data_from_rda",
        "function_overrides": {"buf": 2.0},
        "tpxo_elevation_filepath": "/tpxo/h.nc",
        "tpxo_velocity_filepath": "/tpxo/u.nc",
        "tidal_constituents": ["M2"],
    }
    _type(monkeypatch, None)

    assert ask_forcings(NYF, current) == current
