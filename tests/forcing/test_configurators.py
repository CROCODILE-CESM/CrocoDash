from CrocoDash.forcing.base import *
from CrocoDash.forcing.mom6 import ConditionsConfigurator
from CrocoDash.forcing.tides import TidesConfigurator
from ProConPy.config_var import cvars
from CrocoDash.raw_data_access.base import NOLEAP
import pytest
from fnmatch import fnmatchcase
import re
from types import SimpleNamespace
import pandas as pd

# ---------------------------------------------------------------------------
# Declared output files vs. the files the case settings point at
# ---------------------------------------------------------------------------
#
# The model only reads a file some user_nl or xml value names, so every file a
# configurator declares in output_files() must be named by one, and every file
# in the inputdir that one names must be declared.

# A NetCDF file name inside a namelist or xml value, e.g. the
# "forcing_obc_segment_001.nc" in 'U=file:forcing_obc_segment_001.nc(u)'.
_NC_FILE_REF = re.compile(r"[^\s\"',:=()]+\.nc\b")


def _ctx(inputdir):
    """The parts of a WorkflowContext output_files() reads."""
    return SimpleNamespace(inputdir=inputdir, output_path=inputdir / "ocn")


def case_file_references(configurators, ctx):
    """(files, dirs) in ctx.inputdir that the configurators' user_nl and xml
    values point at. A bare name is relative to MOM6's INPUTDIR,
    ctx.output_path. A dir is a value that is an absolute path to anything but
    a NetCDF file (WW3_GRID_INP_DIR). Files outside the inputdir (inputdata)
    or under extract_forcings/ aren't the case's own."""
    files, dirs = set(), set()
    for configurator in configurators:
        for param in configurator.output_params:
            if param.value is None or not isinstance(
                param, (UserNLConfigParam, XMLConfigParam)
            ):
                continue
            value = str(param.value).strip().strip("\"'")
            # Joining an absolute path onto output_path leaves it as it is.
            files.update(ctx.output_path / ref for ref in _NC_FILE_REF.findall(value))
            if Path(value).is_absolute() and not value.endswith(".nc"):
                dirs.add(Path(value))

    def owned(path):
        return path.is_relative_to(ctx.inputdir) and not path.is_relative_to(
            ctx.inputdir / "extract_forcings"
        )

    return {f for f in files if owned(f)}, {d for d in dirs if owned(d)}


def declared_files(configurators, ctx):
    return {
        Path(path): configurator.name
        for configurator in configurators
        for paths in configurator.output_files(ctx).values()
        for path in paths
    }


def undeclared_references(configurators, ctx):
    """Files a case setting points at that no configurator declares."""
    declared = declared_files(configurators, ctx)
    files, _ = case_file_references(configurators, ctx)
    return sorted(
        f for f in files if not any(fnmatchcase(str(f), str(d)) for d in declared)
    )


def unreferenced_declarations(configurators, ctx):
    """{path: configurator name} for every declared file no case setting
    points at, by name or through its directory."""
    files, dirs = case_file_references(configurators, ctx)
    return {
        path: name
        for path, name in declared_files(configurators, ctx).items()
        if not (
            any(fnmatchcase(str(f), str(path)) for f in files)
            or any(path.is_relative_to(d) for d in dirs)
        )
    }


class _Settings(BaseConfigurator):
    """Not @register'd. Carries whatever case settings and declared files
    (relative to the inputdir) a test gives it."""

    name = "settings"
    process_components = {"files": "process"}
    input_params = []
    output_params = []

    def __init__(self, settings=(), declared=()):
        super().__init__()
        self.output_params = []
        for name, value, kind in settings:
            param = UserNLConfigParam(name) if kind == "nl" else XMLConfigParam(name)
            param.set_item(value)
            self.output_params.append(param)
        self._declared = list(declared)

    def configure(self):
        pass

    def output_files(self, ctx):
        return {"files": [ctx.inputdir / path for path in self._declared]}


def test_case_file_references_resolves_names(tmp_path):
    configurator = _Settings(
        settings=[
            # A bare name is relative to MOM6's INPUTDIR, inputdir/ocn.
            ("CHL_FILE", '"chl.nc"', "nl"),
            # Several names inside one OBC string.
            ("OBC_DATA", '"U=file:seg_001.nc(u),SSH=file:tz_001.nc(z)"', "nl"),
            # Absolute paths under inputdir, quoted or not.
            ("ice_ic", f"'{tmp_path / 'ice' / 'f.nc'}'", "nl"),
            ("MAP", str(tmp_path / "mapping" / "m.nc"), "xml"),
            # A directory.
            ("WAV_DIR", str(tmp_path / "wav"), "xml"),
            # Outside inputdir, or scratch under it: not the case's files.
            ("STREAM", "/inputdata/jra.nc", "nl"),
            ("RAW", str(tmp_path / "extract_forcings" / "raw.nc"), "xml"),
        ]
    )
    files, dirs = case_file_references([configurator], _ctx(tmp_path))
    assert files == {
        tmp_path / "ocn" / "chl.nc",
        tmp_path / "ocn" / "seg_001.nc",
        tmp_path / "ocn" / "tz_001.nc",
        tmp_path / "ice" / "f.nc",
        tmp_path / "mapping" / "m.nc",
    }
    assert dirs == {tmp_path / "wav"}


def test_reference_check_agrees_when_settings_and_declarations_match(tmp_path):
    configurator = _Settings(
        settings=[
            ("CHL_FILE", "chl.nc", "nl"),
            ("WAV_DIR", str(tmp_path / "wav"), "xml"),
        ],
        # A glob under a referenced directory counts as referenced.
        declared=["ocn/chl.nc", "wav/ww3.point*_spec.nc"],
    )
    assert undeclared_references([configurator], _ctx(tmp_path)) == []
    assert unreferenced_declarations([configurator], _ctx(tmp_path)) == {}


def test_reference_check_reports_both_directions(tmp_path):
    configurator = _Settings(
        settings=[("CHL_FILE", "chl.nc", "nl")], declared=["ocn/other.nc"]
    )
    assert undeclared_references([configurator], _ctx(tmp_path)) == [
        tmp_path / "ocn" / "chl.nc"
    ]
    assert unreferenced_declarations([configurator], _ctx(tmp_path)) == {
        tmp_path / "ocn" / "other.nc": "settings"
    }


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


def test_inspect_user_nl(fake_param_case):
    path = fake_param_case
    (path / "user_nl_mom").write_text("test = 42\n")

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


def test_all_configurators_smoke(fake_param_case, fake_cime, fake_forcing_product):

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
            elif a == "boundaries":
                ctor_args[a] = ["south", "north", "west", "east"]
            elif a == "product_name":
                ctor_args[a] = "GLORYS"
            elif a == "ww3_obc_product_name":
                ctor_args[a] = "reference_waves"
            elif a == "cice_product_name":
                ctor_args[a] = "reference_ice"
            elif "filepath" in a:
                ctor_args[a] = dummy_path
            elif "dir" in a:
                ctor_args[a] = dummy_dir
            elif "cime" in a:
                ctor_args[a] = fake_cime
            elif "forcing_product" in a:
                ctor_args[a] = fake_forcing_product
            elif a == "calendar":
                # Typed arg: the configurators expand it with asdict(), so the
                # generic dummy_str fallback below would not do.
                ctor_args[a] = NOLEAP
            else:
                ctor_args[a] = dummy_str
        instance = config_class(**ctor_args)

        # Smoke test
        if hasattr(instance, "output_params") and any(
            isinstance(x, XMLConfigParam) for x in instance.output_params
        ):
            with pytest.raises(RuntimeError):
                instance.configure()
        elif any(isinstance(x, ConfigOutputParam) for x in instance.output_params):
            # ConfigOutputParam values are config.json-only derived values (dates,
            # product metadata, etc.) with no case-directory representation, so
            # they can't be round-tripped through inspect().
            instance.configure()
        else:
            instance.configure()

            # Test inspect (xml is trickier)
            inspect_instance = config_class.inspect(fake_param_case)
            assert inspect_instance == instance

        # Test serialize & unserialize
        ser = instance.serialize()
        deser_instance = config_class.deserialize(ser)
        assert instance == deser_instance

        # Every process step declares its output files, computably from
        # config.json alone, all inside the inputdir, and every file this
        # configurator's own case settings point at is one of them. (The other
        # direction needs the whole registry: conditions' OBC strings name
        # tides' files.) Not the dummy configurators other test modules register.
        if not config_class.__module__.startswith("CrocoDash."):
            continue
        ctx = _ctx(fake_param_case)
        declared = instance.output_files(ctx)
        assert set(declared) == set(config_class.process_components), config_class
        assert deser_instance.output_files(ctx) == declared, config_class
        paths = [path for flag_paths in declared.values() for path in flag_paths]
        assert len(paths) == len(set(paths)), config_class
        for path in paths:
            assert Path(path).is_relative_to(fake_param_case), path
        assert undeclared_references([instance], ctx) == [], config_class


def test_conditions_and_tides_files_match_the_obc_strings(fake_param_case):
    """The conditions OBC strings name its own segment files and tides' tu_/tz_
    files, so the two directions of the reference check only agree across
    both configurators."""
    boundaries = ["south", "north", "east"]
    conditions = ConditionsConfigurator(
        boundaries=boundaries,
        product_name="GLORYS",
        function_name="get_glorys_data_from_rda",
        compset="MOM6",
        date_range=pd.to_datetime(["2000-01-01", "2000-01-02"]),
    )
    conditions.registry = SimpleNamespace(is_active=lambda name: name == "tides")
    conditions.configure()
    tides = TidesConfigurator(
        tpxo_elevation_filepath="h.nc",
        tpxo_velocity_filepath="u.nc",
        tidal_constituents=["M2"],
        boundaries=boundaries,
        start_date="2000, 01, 01",
    )
    tides.configure()

    ctx = _ctx(fake_param_case)
    both = [conditions, tides]
    assert unreferenced_declarations(both, ctx) == {}
    assert undeclared_references(both, ctx) == []
    # On its own, nothing points at the tides files.
    assert set(unreferenced_declarations([tides], ctx)) == set(
        tides.output_files(ctx)["tides"]
    )


"""
Configurators are only smoke tested because the individual parts of the process are tested above and in test_forcing_configuration_registry.
The ONLY additional testing should be if any configuration has unique configuration that has additional complexity.
"""
