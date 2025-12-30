from CrocoDash.forcing_configurations import *
import pytest


@register
class Dummy(BaseConfigurator):
    name = "dummy"
    required_for_compsets = ["req"]
    allowed_compsets = []
    forbidden_compsets = ["for"]
    input_params = [
        InputValueParam(
            "dummy",
            comment="Boop Boop",
        )
    ]
    output_params = []

    def __init__(self, dummy):
        super().__init__(dummy=dummy)

    def configure(self):
        self.x = 1


@register
class Dummy2(BaseConfigurator):
    name = "dummy2"
    required_for_compsets = ["req"]
    allowed_compsets = ["req", "dummy"]
    forbidden_compsets = ["for"]
    input_params = [
        InputValueParam(
            "dummy",
            comment="Boop Boop",
        )
    ]
    output_params = []

    def __init__(self, dummy):
        super().__init__(dummy=dummy)

    def configure(self):
        self.x = 1


@register
class Dummy1(BaseConfigurator):
    name = "dummy1"

    input_params = [
        InputValueParam(
            "dummy",
            comment="Boop Boop",
        )
    ]
    output_params = []

    def __init__(self, dummy):
        super().__init__(dummy=dummy)

    def configure(self):
        self.dummy1 = 1


@pytest.fixture
def fcr_add_dummy1():
    return ForcingConfigRegistry("", {"dummy": "dummy"})


def test_serialize():
    obj_dict = Dummy1("Bleh").serialize()
    assert obj_dict["name"] == "dummy1"
    assert obj_dict["inputs"]["dummy"] == "Bleh"


def test_deserialize():
    obj_dict = {"name": "dummy1", "inputs": {"dummy": "Bleh"}}
    obj = Dummy1.deserialize(obj_dict)
    assert type(obj) == Dummy1
    assert obj.get_input_param("dummy") == "Bleh"


def test_validate_compset_compatability():
    assert Dummy.validate_compset_compatibility("req")
    assert Dummy.validate_compset_compatibility("dummy")
    assert Dummy.validate_compset_compatibility("dummy_req")
    assert Dummy2.validate_compset_compatibility("dummy_req")
    assert not Dummy2.validate_compset_compatibility("req")
    assert not Dummy2.validate_compset_compatibility("for_req_dummy")


def test_is_required():
    assert Dummy.is_required("req")
    assert not Dummy.is_required("dummy")
    assert Dummy.is_required("dummy_req")


def test_FCR_register():
    # --- Dummy config for testing ---
    assert Dummy in ForcingConfigRegistry.registered_types


def test_FCR_find_active_configurators_accessible_and_check_init():
    """Test if you have a properly set up configurator with the right arguments it gets registered, and has required compset and the init works"""
    fcr = ForcingConfigRegistry("req", {"dummy": "dummy"})
    assert fcr.is_active("dummy")
    assert fcr.is_active("dummy1")
    assert type(fcr["dummy1"]) == Dummy1
    assert fcr["dummy1"].get_input_param("dummy") == "dummy"  # check init works


def test_FCR_find_active_configurators_fail_if_required_and_no_valid_args():
    """Test if we can trigger the is_required option andfaily with the wrong args"""
    with pytest.raises(ValueError):
        ForcingConfigRegistry("req", {})


def test_FCR_find_active_configurators_skip_if_no_args():
    """Test if we can trigger skip if the proper args aren't given in dummy1"""

    fcr = ForcingConfigRegistry("", {})
    assert (
        "dummy1" not in fcr.active_configurators
    )  # active configurators should be empty


def test_FCR_configure(fcr_add_dummy1):
    fcr = fcr_add_dummy1
    fcr.run_configurators()
    assert fcr["dummy1"].dummy1 == 1
