from CrocoDash.forcing_configurations import *
from ProConPy.config_var import cvars
import pytest
from types import SimpleNamespace
import pandas as pd


@pytest.fixture
def fake_param_case(tmp_path):
    cvars["CASEROOT"] = SimpleNamespace(value=None)
    cvars["CUSTOM_ROF_GRID"] = SimpleNamespace(value=None)
    cvars["NINST"] = SimpleNamespace(value=None)
    cvars["NINST"].value = None
    cvars["CASEROOT"].value = tmp_path
    cvars["CUSTOM_ROF_GRID"].value = "s"

    (tmp_path / "user_nl_mom").touch()
    (tmp_path / "user_nl_cice").touch()
    return tmp_path


def test_user_nl_mom_apply(fake_param_case):
    path = fake_param_case
    s = UserNLConfigParam("test")
    s.set_item("test")
    s.apply()
    fname = path / "user_nl_mom"

    with open(fname) as f:
        contents = f.read()

    assert "test = test" in contents


def test_inspect_user_nl(fake_param_case):
    path = fake_param_case
    s = UserNLConfigParam("test")
    s.set_item("42")
    s.apply()

    reciever = UserNLConfigParam("test")
    reciever.inspect(caseroot=path)

    assert reciever.value == "42"


def test_xml_apply(fake_param_case):
    with pytest.raises(RuntimeError):  # This is not a real case
        s = XMLConfigParam("test")
        s.set_item("test")
        s.apply()


def test_all_configurators_args_synced():

    for config_class in ForcingConfigRegistry.registered_types:

        config_class.check_input_params_synced()
        config_class.check_output_params_exist()


def test_all_configurators_smoke(fake_param_case):

    ## Set up some dummy args
    dummy_str = "123"
    dummy_date_range = ["2000-01-01", "2000-01-02"]
    dummy_date_range = pd.to_datetime(dummy_date_range)
    dummy_path = fake_param_case / "dummy_path"
    dummy_dir = fake_param_case
    dummy_path.touch()

    ## Iterate through config classes
    for config_class in ForcingConfigRegistry.registered_types:
        # Test the init and configuration
        sig = inspect.signature(config_class.__init__)
        args = [p.name for p in sig.parameters.values() if p.name != "self"]
        ctor_args = {}
        for a in args:
            if a == "date_range":
                ctor_args[a] = dummy_date_range
            elif "filepath" in a:
                ctor_args[a] = dummy_path
            elif "dir" in a:
                ctor_args[a] = dummy_dir
            else:
                ctor_args[a] = dummy_str
        instance = config_class(**ctor_args)

        if hasattr(instance, "output_params") and any(
            isinstance(x, XMLConfigParam) for x in instance.output_params
        ):
            with pytest.raises(RuntimeError):
                instance.configure()
        else:
            instance.configure()


"""
Configurators are only smoke tested because the individual parts of the process are tested above and in test_forcing_configuration_registry.
The ONLY additional testing should be if any configuration has unique configuration that has additional complexity.
"""
