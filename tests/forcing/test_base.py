from CrocoDash.forcing.base import *

from types import SimpleNamespace
from unittest.mock import patch

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


class DummyXML(BaseConfigurator):
    """Exercises the XMLConfigParam is_non_local path without declaring a
    case_is_non_local input param -- see test_is_non_local_* below. Not
    @register'd: it only needs direct construction, and registering it would
    make it an active configurator in every other test in this module too."""

    name = "dummyxml"

    input_params = [
        InputValueParam(
            "dummy",
            comment="Boop Boop",
        )
    ]
    output_params = [
        XMLConfigParam("DUMMY_XML_VAR", comment="Boop Boop"),
    ]

    def __init__(self, dummy):
        super().__init__(dummy=dummy)

    def configure(self):
        self.set_output_param("DUMMY_XML_VAR", "value")
        super().configure()


class DummyUserNL(BaseConfigurator):
    """UserNLConfigParam counterpart to DummyXML, for the do_exec tests below.
    Not @register'd, for the same reason DummyXML isn't."""

    name = "dummyusernl"

    input_params = [
        InputValueParam(
            "dummy",
            comment="Boop Boop",
        )
    ]
    output_params = [
        UserNLConfigParam("DUMMY_NL_VAR", comment="Boop Boop"),
    ]

    def __init__(self, dummy):
        super().__init__(dummy=dummy)

    def configure(self):
        self.set_output_param("DUMMY_NL_VAR", "value")
        super().configure()


@pytest.fixture
def fcr_add_dummy1():
    return ForcingConfigRegistry("", {"dummy": "dummy"}, None)


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
    fcr = ForcingConfigRegistry("req", {"dummy": "dummy"}, None)
    assert fcr.is_active("dummy")
    assert fcr.is_active("dummy1")
    assert type(fcr["dummy1"]) == Dummy1
    assert fcr["dummy1"].get_input_param("dummy") == "dummy"  # check init works


def test_FCR_find_active_configurators_fail_if_required_and_no_valid_args():
    """Test if we can trigger the is_required option andfaily with the wrong args"""
    with pytest.raises(ValueError):
        ForcingConfigRegistry("req", {}, None)


def test_FCR_find_active_configurators_skip_if_no_args():
    """Test if we can trigger skip if the proper args aren't given in dummy1"""

    fcr = ForcingConfigRegistry("", {}, None)
    assert (
        "dummy1" not in fcr.active_configurators
    )  # active configurators should be empty


def test_FCR_configure(fcr_add_dummy1):
    fcr = fcr_add_dummy1
    fcr.run_configurators(None)
    assert fcr["dummy1"].dummy1 == 1


@patch("CrocoDash.forcing.base.xmlchange")
def test_is_non_local_defaults_false_without_case(mock_xmlchange):
    """Direct construction (no registry/case, e.g. in a unit test) -- an
    XMLConfigParam output still applies, defaulting is_non_local False,
    without DummyXML declaring a case_is_non_local input param."""
    obj = DummyXML("x")
    obj.configure()
    mock_xmlchange.assert_called_once_with(
        "DUMMY_XML_VAR", "value", do_exec=True, is_non_local=False
    )


@patch("CrocoDash.forcing.base.xmlchange")
def test_is_non_local_propagates_from_registry_case(mock_xmlchange):
    """A configurator whose registry points at a non-local Case -- is_non_local
    reaches XMLConfigParam.apply() automatically, sourced from the Case
    rather than threaded through DummyXML's own inputs."""
    obj = DummyXML("x")
    obj.registry = SimpleNamespace(case=SimpleNamespace(is_non_local=True))
    obj.configure()
    mock_xmlchange.assert_called_once_with(
        "DUMMY_XML_VAR", "value", do_exec=True, is_non_local=True
    )


@patch("CrocoDash.forcing.base.xmlchange")
def test_do_exec_defaults_true_without_case(mock_xmlchange):
    """No live Case (direct construction, deserialize()) must keep executing.

    do_exec's default is the opposite of is_non_local's: True, so that every
    existing caller behaves exactly as it did before do_exec existed.
    """
    obj = DummyXML("x")
    obj.configure()
    assert mock_xmlchange.call_args.kwargs["do_exec"] is True


@patch("CrocoDash.forcing.base.xmlchange")
def test_do_exec_propagates_from_registry_case(mock_xmlchange):
    """A Case configured but never created (MACHINE == CESM_NOT_PORTED) must not
    shell out to xmlchange -- there is no case directory to run it in."""
    obj = DummyXML("x")
    obj.registry = SimpleNamespace(case=SimpleNamespace(do_exec=False))
    obj.configure()
    assert mock_xmlchange.call_args.kwargs["do_exec"] is False


@patch("CrocoDash.forcing.base.append_user_nl")
def test_do_exec_propagates_to_user_nl_params(mock_append_user_nl):
    """do_exec must also reach UserNLConfigParam, which (unlike XMLConfigParam)
    previously hardcoded do_exec=True in apply()."""
    obj = DummyUserNL("x")
    obj.registry = SimpleNamespace(case=SimpleNamespace(do_exec=False))
    obj.configure()
    assert mock_append_user_nl.call_args.kwargs["do_exec"] is False


@patch("CrocoDash.forcing.base.append_user_nl")
def test_user_nl_do_exec_defaults_true_without_case(mock_append_user_nl):
    """Same default-True guarantee as the XML path, for user_nl writes."""
    obj = DummyUserNL("x")
    obj.configure()
    assert mock_append_user_nl.call_args.kwargs["do_exec"] is True


def test_depends_on_outputs_targets_exist():
    """Every declared cross-configurator dependency (depends_on_outputs)
    must name a real, registered configurator and a real output param on
    it -- catches a stale reference (e.g. after a rename) statically,
    instead of a bare KeyError only surfacing at process-time deep inside
    ForcingConfigRegistry.get_configurator_output()."""
    for configurator_cls in ForcingConfigRegistry.registered_types:
        for dep_name, output_names in configurator_cls.depends_on_outputs.items():
            dep_cls = ForcingConfigRegistry.get_configurator_from_name(dep_name)
            declared_outputs = {p.name for p in dep_cls.output_params}
            missing = set(output_names) - declared_outputs
            assert not missing, (
                f"{configurator_cls.__name__}.depends_on_outputs references "
                f"{dep_name!r}.{sorted(missing)}, but {dep_cls.__name__} has no "
                f"such output_params (has: {sorted(declared_outputs)})"
            )
