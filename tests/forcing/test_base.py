from CrocoDash.forcing.base import *

import ast
import json
import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import CrocoDash
from CrocoDash.raw_data_access.registry import ProductRegistry


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


def test_deserialize_tolerates_entries_from_other_versions():
    """An entry with an undeclared key and a missing output still loads; one
    missing a required input asks for configure_forcings() to be rerun."""
    obj = DummyXML.deserialize({"inputs": {"dummy": "x", "gone": 1}, "outputs": {}})
    assert obj.get_output_param("DUMMY_XML_VAR") is None
    with pytest.raises(ReconfigureRequired):
        DummyXML.deserialize({"inputs": {}, "outputs": {}})


def test_read_config_versions(tmp_path):
    """An unversioned config.json reads as 1.0.0; one from a newer CrocoDash
    is refused rather than misread."""
    path = tmp_path / CONFIG_FILENAME
    path.write_text(json.dumps({"caseroot": "/case"}))
    assert read_config(path)["schema_version"] == "1.0.0"
    path.write_text(json.dumps({"schema_version": "1.1.0", "caseroot": "/case"}))
    with pytest.raises(ValueError):
        read_config(path)


@pytest.mark.parametrize(
    "path",
    sorted((Path(__file__).parent / "golden_configs").glob("*.json")),
    ids=lambda path: path.stem,
)
def test_golden_configs_load(path):
    """config.json files real cases wrote with earlier CrocoDash versions
    still load. Add one here when a change could break old configs."""
    ProductRegistry.load()
    ForcingConfigRegistry.resolve_process_targets(read_config(path))


def test_config_json_is_only_read_through_read_config():
    """A bare "config.json" outside base.py means a reader that skips the
    version check in read_config()."""
    package = Path(CrocoDash.__file__).parent
    offenders = []
    for path in package.rglob("*.py"):
        relative = path.relative_to(package)
        if relative.parts[0] in {"rm6", "visualCaseGen", "gallery"}:
            continue
        if relative == Path("forcing/base.py"):
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Constant) and re.fullmatch(
                r"\S*config\.json", str(node.value)
            ):
                offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, offenders


@pytest.mark.parametrize(
    "compset, required",
    [
        ("1850_DATM%JRA_SLND_SICE_MOM6%REGIONAL_SROF_SGLC_SWAV", {"date_range"}),
        (
            "1850_DATM%JRA_SLND_SICE_MOM6%MARBL-BIO%REGIONAL_DROF%GLOFAS_SGLC_SWAV",
            {"date_range", "marbl_ic_filepath"},
        ),
    ],
)
def test_param_specs_list_what_the_compset_needs(compset, required):
    """A front-end asks for the required inputs, and never for one the Case
    fills in or the configurators derive."""
    specs = ForcingConfigRegistry.param_specs(compset)
    assert {spec.name for spec in specs if spec.required} == required
    names = {spec.name for spec in specs}
    assert not {name for name in names if name.startswith("case_")}
    assert not names & {
        "compset",
        "start_date",
        "end_date",
        "calendar",
        "function_args",
    }


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
    fcr.run_configurators()
    assert fcr["dummy1"].dummy1 == 1


@patch("CrocoDash.forcing.base.xmlchange")
def test_is_non_local_defaults_false_without_case(mock_xmlchange):
    """Direct construction (no registry/case, e.g. in a unit test) -- an
    XMLConfigParam output still applies, defaulting is_non_local False,
    without DummyXML declaring a case_is_non_local input param."""
    obj = DummyXML("x")
    obj.configure()
    mock_xmlchange.assert_called_once_with(
        "DUMMY_XML_VAR", "value", caseroot=None, is_non_local=False
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
        "DUMMY_XML_VAR", "value", caseroot=None, is_non_local=True
    )


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


class DummyUserNL(BaseConfigurator):
    """Not @register'd, for the same reason as DummyXML."""

    name = "dummyusernl"
    input_params = [InputValueParam("dummy", comment="Boop Boop")]
    output_params = [
        UserNLConfigParam("ice_a", user_nl_name="cice", comment="first"),
        UserNLConfigParam("ocn_a", user_nl_name="mom", comment="ocean"),
        UserNLConfigParam("ice_b", user_nl_name="cice", comment="second"),
        UserNLConfigParam("ice_c", user_nl_name="cice", comment="third"),
    ]

    def __init__(self, dummy):
        super().__init__(dummy=dummy)

    def configure(self):
        for i, p in enumerate(self.output_params):
            self.set_output_param(p.name, i)
        super().configure()


def test_user_nl_block_per_file(tmp_path):
    """A configurator's parameters for one file go into one CrocoDash block,
    each with its own comment."""
    obj = DummyUserNL("x")
    obj.registry = SimpleNamespace(case=SimpleNamespace(caseroot=tmp_path, ninst=1))
    obj.configure()

    cice = (tmp_path / "user_nl_cice").read_text().splitlines()
    assert sum(line.startswith("! >>> CrocoDash") for line in cice) == 1
    assert [line for line in cice if line and not line.startswith("! ")] == [
        "ice_a = 0",
        "ice_b = 2",
        "ice_c = 3",
    ]
    assert [line for line in cice if line in ("! first", "! second", "! third")] == [
        "! first",
        "! second",
        "! third",
    ]
    assert "ocn_a = 1" in (tmp_path / "user_nl_mom").read_text()


def test_two_cases_in_one_process_each_write_to_their_own_caseroot(tmp_path):
    """visualCaseGen's global CASEROOT is the case created last, so configuring
    the first of two cases used to write into the second."""
    caseroots = [tmp_path / "first", tmp_path / "second"]
    configurators = []
    for caseroot in caseroots:
        caseroot.mkdir()
        registry = SimpleNamespace(case=SimpleNamespace(caseroot=caseroot, ninst=1))
        for obj in (DummyUserNL("x"), DummyXML("x")):
            obj.registry = registry
            configurators.append(obj)

    with patch("CrocoDash.forcing.base.subprocess.run") as run:
        run.return_value.returncode = 0
        for obj in configurators:
            obj.configure()

    for caseroot in caseroots:
        assert "ice_a = 0" in (caseroot / "user_nl_cice").read_text()
    assert [call.kwargs["cwd"] for call in run.call_args_list] == caseroots
