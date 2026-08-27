import pytest

from CrocoDash.extract_forcings import mom6
from CrocoDash.forcing_configurations.configurations import ConditionsConfigurator


def test_build_forcing_request_merges_function_args():
    product_info = {
        "u_var_name": "uo",
        "v_var_name": "vo",
        "eta_var_name": "zos",
        "tracer_var_names": {"temp": "thetao", "salt": "so"},
        "dataset_path": "/some/path",
    }

    variables, extra_args = mom6.build_forcing_request(
        product_info, function_args={"member": 5}
    )

    assert extra_args["dataset_path"] == "/some/path"
    assert extra_args["member"] == 5


# =============================================================================
# ConditionsConfigurator.validate_args
# =============================================================================


def _conditions(product_name):
    return ConditionsConfigurator(
        boundaries=["north"],
        product_name=product_name,
        function_name="get_glorys_data_script_for_cli",
        compset="1850_DATM%JRA_SLND_SICE_MOM6%REGIONAL_SROF_SGLC_SWAV",
        start_date="20200101",
        end_date="20200102",
    )


def test_conditions_configurator_rejects_non_mom6_product():
    # A registered product of the wrong flavor (GLOFAS river discharge) and an
    # entirely unknown name are both rejected, with distinct messages.
    with pytest.raises(ValueError, match="not a MOM6ForcingProduct"):
        _conditions("glofas")

    with pytest.raises(ValueError, match="Unknown forcing product"):
        _conditions("not_a_real_product")


def test_conditions_configurator_accepts_mom6_products():
    # Doesn't raise -- GLORYS plus the CESM POP/MOM output readers all feed the
    # MOM6 IC/OBC pipeline.
    _conditions("glorys")
    _conditions("cesm_pop_output")
    _conditions("cesm_mom_output")
