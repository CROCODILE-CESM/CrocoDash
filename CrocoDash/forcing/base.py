from pathlib import Path
from typing import List, Dict
from abc import ABC, abstractmethod
from functools import cached_property
from visualCaseGen.custom_widget_types.case_tools import xmlchange
from CrocoDash.forcing import user_nl_blocks
from CrocoDash import case_state
from CrocoDash.logging import setup_logger
import inspect
from typing import Optional, Any
import copy
import subprocess
import json
import dataclasses
from CrocoDash.raw_data_access.base import Calendar
from CrocoDash.raw_data_access.registry import ProductRegistry

logger = setup_logger(__name__)

# The forcing configuration Case.configure_forcings() writes to
# <inputdir>/extract_forcings/config.json: one entry per active configurator,
# plus the top-level CONFIG_META_KEYS. Read it only through read_config(), which
# rejects a config.json written by an incompatible CrocoDash (MAJOR.MINOR must
# match, as for the case state file). Entries are read tolerantly (see
# BaseConfigurator.deserialize), so bump the MINOR only when that would misread
# an old file, e.g. after a rename, and add a CONFIG_MIGRATIONS entry for it.
# See docs/source/for_developers/config_compatibility.md.
CONFIG_FILENAME = "config.json"
CONFIG_SCHEMA_VERSION = "1.0.0"
# What a config.json written before versioning is read as.
CONFIG_UNVERSIONED = "1.0.0"
CONFIG_META_KEYS = frozenset({"schema_version", "caseroot"})


def write_config(path, config):
    """Write *config* to *path*, injecting schema_version as the first key."""
    full_config = {"schema_version": CONFIG_SCHEMA_VERSION, **config}
    with open(path, "w") as f:
        json.dump(full_config, f, indent=4)


# Upgrades for config.json files an older CrocoDash wrote, keyed by the
# "MAJOR.MINOR" they upgrade from. Each takes the config dict and returns it at
# the next version.
CONFIG_MIGRATIONS = {}


def read_config(path):
    """Read the config.json at *path*, upgrade it if a migration applies,
    validate its schema version, and return it."""
    with open(path) as f:
        config = json.load(f)
    config.setdefault("schema_version", CONFIG_UNVERSIONED)
    while (from_version := config["schema_version"].rsplit(".", 1)[0]) in (
        CONFIG_MIGRATIONS
    ):
        config = CONFIG_MIGRATIONS[from_version](config)
    case_state.check_version(config, path, supported=CONFIG_SCHEMA_VERSION)
    return config


def calendar_as_dict(calendar):
    """Store a Calendar in config.json as a plain dict, leaving anything else be.

    A configurator is normally constructed from a live Calendar, but also from
    the serialized dict (BaseConfigurator.deserialize) and from empty
    placeholders (BaseConfigurator.inspect), so only the dataclass is
    converted here.
    """
    if isinstance(calendar, Calendar):
        return dataclasses.asdict(calendar)
    return calendar


def product_choices(product_type, *extra):
    """choices= for a product-name input: the products of product_type, plus extra."""
    return lambda values: sorted(
        (
            product.product_name
            for product in ProductRegistry.products.values()
            if issubclass(product, product_type)
        ),
        key=str.lower,
    ) + list(extra)


def access_method_choices(product_input):
    """choices= for a function-name input: the access methods of the product
    that the product_input input names."""

    def choices(values):
        product = values.get(product_input)
        if product and ProductRegistry.product_exists(product):
            return ProductRegistry.list_access_methods(product)
        return None

    return choices


class ReconfigureRequired(ValueError):
    """config.json lacks something this version of CrocoDash needs, so the
    case's forcings must be configured again before they can be processed."""


class UndeclaredParamError(KeyError):
    """Code referenced an input/output param name that isn't declared on the
    class (a schema bug, e.g. a stale name after a rename). Kept as a
    KeyError subclass so existing `except KeyError` call sites are
    unaffected, but a distinct type so a param-consistency check can catch
    exactly this failure and not any other incidental KeyError raised by a
    configurator's own business logic."""


def register(cls):
    """Decorator: register a BaseConfigurator subclass with ForcingConfigRegistry.

    Every module under CrocoDash.forcing that defines a configurator class
    applies this at class-definition time; CrocoDash.forcing/__init__.py's
    auto-discovery ensures those modules (and hence this decorator) run for
    every file in the package, so adding a new forcing type is just adding a
    new file here -- nothing else needs to import it by name.
    """
    ForcingConfigRegistry.register(cls)
    return cls


class WorkflowContext:
    """Workflow-level paths shared by every configurator's process step.

    Built once by driver.run_workflow() from config.json + case_state, and
    passed into every ``process_*(ctx)`` call. These are paths no single
    configurator owns (they're not part of any configurator's own inputs/
    outputs) but that most process steps need -- grid/topo/vgrid files and
    the raw/regridded/output directories for this case.
    """

    def __init__(
        self,
        inputdir: Path,
        supergrid_path: Path,
        vgrid_path: Path,
        topo_path: Path,
        raw_data_dir: Path,
        regridded_data_dir: Path,
        output_path: Path,
        config: dict,
        preview: bool = False,
    ):
        self.inputdir = Path(inputdir)
        self.supergrid_path = Path(supergrid_path)
        self.vgrid_path = Path(vgrid_path)
        self.topo_path = Path(topo_path)
        self.raw_data_dir = Path(raw_data_dir)
        self.regridded_data_dir = Path(regridded_data_dir)
        self.output_path = Path(output_path)
        self.config = config
        self.preview = preview

    @cached_property
    def grid(self):
        from CrocoDash.grid import Grid

        return Grid.from_supergrid(self.supergrid_path)

    @cached_property
    def ocn_topo(self):
        from CrocoDash.topo import Topo
        from CrocoDash.forcing.utils import read_min_depth

        return Topo.from_topo_file(
            self.grid,
            self.topo_path,
            min_depth=read_min_depth(self.topo_path),
            git=False,
        )


class ForcingConfigRegistry:
    registered_types: List[type] = []

    @classmethod
    def register(cls, configurator_cls: type):

        cls.registered_types.append(configurator_cls)

    def __getitem__(self, key: str):
        return self.active_configurators[key.lower()]

    def __init__(self, compset, inputs: dict, case=None):
        self.compset = compset
        self.case = case
        self.active_configurators = {}
        given = set(inputs)
        if case is not None:
            self.case_info = {
                f"case_{k}": v
                for k, v in case.__dict__.items()
                if not k.startswith("_")
            }
            inputs = inputs | self.case_info
        inputs["compset"] = compset
        self.find_active_configurators(self.compset, inputs)
        taken = set()
        for configurator in self.active_configurators.values():
            configurator.registry = self
            taken.update(self.get_ctor_signature(type(configurator))[0])
        ignored = sorted(given - taken)
        if ignored:
            logger.warning(
                f"No active forcing configurator takes {ignored}, so they are "
                "ignored. A configurator is active only if the compset allows it "
                "and every argument it needs is given."
            )

    @classmethod
    def get_configurator_from_name(cls, name):
        for thing in cls.registered_types:
            if name.lower() == thing.name.lower():
                return thing
        raise ValueError("Configurator Not Found")

    @classmethod
    def get_configurator(cls, obj_dict):
        return cls.get_configurator_from_name(obj_dict["name"]).deserialize(obj_dict)

    @classmethod
    def find_valid_configurators(cls, compset):
        """Returns the valid configurations based on the compset in a list"""
        valid_configs = []
        for configurator_cls in cls.registered_types:
            if configurator_cls.validate_compset_compatibility(compset):
                valid_configs.append(configurator_cls)
        return valid_configs

    @classmethod
    def find_required_configurators(cls, compset):
        """Returns the required configurations based on the compset in a list"""
        required_configs = []
        for configurator_cls in cls.registered_types:
            if configurator_cls.is_required(compset):
                required_configs.append(configurator_cls)
        return required_configs

    @classmethod
    def param_specs(cls, compset, config=None):
        """The arguments configure_forcings() takes for compset: a ParamSpec for
        each input of every configurator the compset requires or allows.

        Derived inputs and the case_* ones the Case fills in are left out. A
        name several configurators take (boundaries) is listed once, as the
        first of them declares it: one value goes to all of them. Given config
        (a config.json dict), each default is the value it holds instead.
        """
        ProductRegistry.load()
        specs = {}
        for configurator_cls in cls.registered_types:
            required = configurator_cls.is_required(compset)
            if not (
                required or configurator_cls.validate_compset_compatibility(compset)
            ):
                continue
            entry = (config or {}).get(configurator_cls.name.lower(), {})
            for spec in configurator_cls.param_specs(required, entry.get("inputs", {})):
                specs.setdefault(spec.name, spec)
        return list(specs.values())

    @classmethod
    def get_ctor_signature(cls, configurator_cls):
        sig = inspect.signature(configurator_cls.__init__)
        args = [p.name for p in sig.parameters.values() if p.name != "self"]
        required_args = [
            p.name
            for p in sig.parameters.values()
            if p.name != "self" and p.default is inspect._empty
        ]

        return args, required_args

    @classmethod
    def get_user_args(cls, configurator_cls):
        args, required_args = cls.get_ctor_signature(configurator_cls)
        user_args = [arg for arg in required_args if not arg.startswith("case_")]
        return user_args

    @classmethod
    def return_missing_inputs(cls, configurator_cls, inputs):
        _, required_args = cls.get_ctor_signature(configurator_cls)
        missing = [arg for arg in required_args if arg not in inputs]
        return missing

    @classmethod
    def instantiate_configurator(cls, configurator_cls, inputs):
        args, _ = cls.get_ctor_signature(configurator_cls)
        ctor_kwargs = {arg: inputs[arg] for arg in args if arg in inputs}
        return configurator_cls(**ctor_kwargs)

    def find_active_configurators(self, compset, inputs: dict):

        required = self.find_required_configurators(compset)
        valid = self.find_valid_configurators(compset)

        for configurator_cls in self.registered_types:
            name = configurator_cls.name
            lname = name.lower()
            if configurator_cls in required:
                missing = self.return_missing_inputs(configurator_cls, inputs)
                if missing:
                    raise ValueError(
                        f"[ERROR] Required configurator {name} missing args: {missing}"
                    )
                logger.info(f"[REQUIRED] Activating {name}")
                self.active_configurators[lname] = self.instantiate_configurator(
                    configurator_cls, inputs
                )
                continue  # We do not want to to be added twice with the valid configs

            # --- OPTIONAL CONFIGURATORS ---
            if configurator_cls not in valid:
                logger.info(f"[SKIP] {name} incompatible with compset")
                continue

            missing = self.return_missing_inputs(configurator_cls, inputs)
            if missing:
                logger.info(f"[SKIP] {name} missing args: {missing}")
                continue

            logger.info(f"[OPTIONAL] Activating {name}")
            self.active_configurators[lname] = self.instantiate_configurator(
                configurator_cls, inputs
            )

    def run_configurators(self):
        general_config = {}
        for configurator in self.active_configurators.values():
            logger.info(f"Configuring {configurator.name}")
            configurator.configure()
            general_config[configurator.name.lower()] = configurator.serialize()
        return general_config

    def stale_outputs(self, previous_config, current_config, inputdir):
        """Every active configurator's stale_outputs()."""
        # Compare like with like: previous_config was read back from JSON.
        current_config = json.loads(json.dumps(current_config))
        stale = []
        for configurator in self.active_configurators.values():
            stale += configurator.stale_outputs(
                previous_config, current_config, Path(inputdir)
            )
        return stale

    def get_active_configurators(self):
        return self.active_configurators.keys()

    def is_active(self, name: str) -> bool:
        """Return True if a configurator with this name is active."""
        return name.lower() in self.active_configurators

    @classmethod
    def all_process_flags(cls):
        """Every process-component flag name any registered configurator can
        answer to, regardless of whether it's active for a given case --
        used to build cli.py's argparse flags generically."""
        flags = set()
        for configurator_cls in cls.registered_types:
            flags.update(configurator_cls.process_components.keys())
        return flags

    @classmethod
    def available_process_flags(cls, config: dict):
        """Every process-component flag name available given which forcing
        types are present in a config.json dict -- looked up from each
        entry's declared class only (no full deserialize), so this works
        even when an entry's inputs/outputs aren't fully valid yet. Used by
        resolve_components/cli.py to answer "does this flag exist" without
        needing working configurator instances the way actual dispatch does."""
        flags = set()
        for key, entry in config.items():
            if key in CONFIG_META_KEYS:
                continue
            configurator_cls = cls.get_configurator_from_name(entry["name"])
            flags.update(configurator_cls.process_components.keys())
        return flags

    @classmethod
    def resolve_process_targets(cls, config: dict):
        """Deserialize every configurator present in a config.json dict and
        return {flag_name: (configurator_instance, method_name)} covering
        every process component any of them declare. Used by driver.py to
        dispatch generically instead of a hand-maintained if-ladder."""
        targets = {}
        for key, entry in config.items():
            if key in CONFIG_META_KEYS:
                continue
            configurator = cls.get_configurator(entry)
            for flag_name, method_name in configurator.process_components.items():
                targets[flag_name] = (configurator, method_name)
        return targets

    @classmethod
    def get_configurator_output(
        cls, config: dict, configurator_name: str, output_name: str
    ):
        """Look up another configurator's serialized output value from
        config.json -- for a process_*() method that depends on a sibling's
        output but (unlike configure()) can't rely on a live registry/Case,
        since process() may run in a different process. Raises a clear,
        named error instead of a bare KeyError several dict levels deep if
        the dependency isn't there (e.g. the sibling hasn't run yet, or
        never configured this case)."""
        key = configurator_name.lower()
        if key not in config:
            raise KeyError(
                f"Configurator '{configurator_name}' not found in config.json -- "
                f"is it active/configured for this case?"
            )
        outputs = config[key].get("outputs", {})
        if output_name not in outputs:
            raise KeyError(
                f"Configurator '{configurator_name}' has no output '{output_name}' "
                f"in config.json (available: {sorted(outputs)})"
            )
        return outputs[output_name]


class Param(ABC):
    """
    Base class for a single parameter in our forcing configurations.
    """

    def __init__(self, name: str, comment: Optional[str] = None):
        self.name = name
        self.comment = comment

    @abstractmethod
    def set_item(self, item: Any):
        """Bind a runtime value to this parameter."""
        pass

    def __repr__(self):
        return f"{self.__class__.__name__}(name={self.name!r})"


class InputParam(Param):
    """
    A configurator input, stored in config.json.

    derived: the configurator computes it from other arguments (start_date
    from date_range, say), so no one is asked for it.
    choices: a function of the other inputs' values ({name: value}) that
    returns the values this one may take, or None when they aren't known.
    """

    def __init__(
        self,
        name: str,
        comment: Optional[str] = None,
        derived: bool = False,
        choices=None,
    ):
        super().__init__(name, comment)
        self.value: Any = None
        self.derived = derived
        self.choices = choices

    def set_item(self, item):
        self.value = item


class InputValueParam(InputParam):
    """A single value parameter in our forcing configurations."""


class InputFileParam(InputParam):
    """A file path parameter: a front-end treats it as machine-specific."""


@dataclasses.dataclass
class ParamSpec:
    """A configure_forcings() argument, described for a front-end (the Case
    creation printout, prompts, an annotated YAML, the MCP server).

    required: the compset needs it and it has no default. An optional
    configurator's inputs are never required; it is active only when all of
    its inputs without a default are given.
    default: the constructor default, or the value a config.json holds.
    is_path: a file path, which may not exist on another machine.
    choices: the values it may take, when they're known (product names
    match case-insensitively).
    """

    name: str
    configurator: str
    required: bool
    default: Any = None
    comment: Optional[str] = None
    is_path: bool = False
    choices: Optional[List[Any]] = None


class OutputParam(Param):
    """
    Base class for a single configuration parameter applied to a CESM/MOM6 case.

    Subclasses apply themselves (``apply()``), except UserNLConfigParam, which
    BaseConfigurator.configure() writes through user_nl_blocks.
    """

    def __init__(self, name: str, comment: Optional[str] = None, is_file: bool = False):
        super().__init__(name, comment)
        self.value: Any = None
        self.executed: bool = False
        self.is_file = is_file

    def set_item(self, value: Any):
        self.value = value

    @abstractmethod
    def inspect(cls, caseroot):
        """Inspect the current value of this parameter in the case located at caseroot."""
        pass


class UserNLConfigParam(OutputParam):
    """
    Parameter written to a `user_nl_<component>` file (default: user_nl_mom),
    inside its configurator's CrocoDash block (see BaseConfigurator.configure).
    """

    def __init__(
        self,
        name: str,
        user_nl_name: str = "mom",
        comment: Optional[str] = None,
        is_file: bool = False,
    ):
        super().__init__(name, comment, is_file=is_file)
        self.user_nl_name = user_nl_name

    def pair(self):
        """The (name, value) this parameter writes."""
        if self.value is None:
            raise ValueError(f"Value for parameter {self.name} has not been set.")
        return (self.name, self.value)

    def inspect(self, caseroot):
        if self.value is not None:
            raise ValueError(f"Value for parameter {self.name} has already been set.")
        # Using caseroot, get to user_nl
        user_nl_path = Path(caseroot) / f"user_nl_{self.user_nl_name}"
        if not user_nl_path.exists():
            raise FileNotFoundError(f"{user_nl_path} does not exist.")
        # parse user_nl to find the parameter value
        with open(user_nl_path, "r") as f:
            for line in f:
                if line.strip().startswith(self.name):
                    # extract the value
                    _, value = line.split("=", 1)
                    self.executed = True
                    self.value = value.strip()
                    return
        raise KeyError(f"Parameter {self.name} not found in {user_nl_path }")


class XMLConfigParam(OutputParam):
    """
    Parameter applied via xmlchange.

    XML changes are permanent and do not save previous state.
    """

    def __init__(
        self,
        name: str,
        is_non_local: bool = False,
        comment: Optional[str] = None,
        is_file: bool = False,
    ):
        super().__init__(name, comment, is_file=is_file)
        self.is_non_local = is_non_local

    def apply(self):
        if self.value is None:
            raise ValueError(f"Value for parameter {self.name} has not been set.")

        xmlchange(
            self.name,
            str(self.value),
            is_non_local=self.is_non_local,
        )
        self.executed = True

    def inspect(self, caseroot):
        if self.value is not None:
            raise ValueError(f"Value for parameter {self.name} has already been set.")
        # Using caseroot, query xml
        cmd = f"./xmlquery {self.name}"
        if self.is_non_local is True:
            cmd += " --non-local"

        runout = subprocess.run(cmd, shell=True, capture_output=True, cwd=caseroot)
        self.set_item(runout.stdout.decode().strip())


class ConfigOutputParam(OutputParam):
    """
    Derived value with no case-side effect (not written to user_nl or xmlchange'd).

    Exists purely so `set_output_param()` + the generic `serialize()` pick it up
    under a configurator's `outputs`, for values consumed only via config.json
    (e.g. by a sibling configurator's `process_*` method).
    """

    def apply(self):
        if self.value is None:
            raise ValueError(f"Value for parameter {self.name} has not been set.")
        self.executed = True

    def inspect(self, caseroot):
        pass


class BaseConfigurator(ABC):
    """Base class for all CrocoDash configurators."""

    # ---- class-level declarative metadata ----
    name: str = ""

    required_for_compsets: List[str] = []
    allowed_compsets: List[str] = []
    forbidden_compsets: List[str] = []

    input_params: List[Param]
    output_params: List[OutputParam]

    # {cli_flag_name: method_name} -- what this configurator's process step(s)
    # answer to. A configurator with no process step (e.g. one that only sets
    # namelist defaults) leaves this empty. A configurator whose forcing type
    # is one-to-many (e.g. "conditions" produces both ic and bc) declares more
    # than one entry, each naming its own method.
    process_components: Dict[str, str] = {}

    # {configurator_name: [output_names]} -- other configurators' outputs
    # this class's process_*() methods read via
    # ForcingConfigRegistry.get_configurator_output() (process() may run in a
    # different process than configure(), so it can't rely on a live
    # registry -- it goes through the serialized config.json instead).
    # Declaring the dependency here (rather than reaching into
    # ctx.config[...] with no record of the coupling) lets driver.py derive
    # processing order automatically, and lets a test statically confirm the
    # named output actually exists on the target class -- instead of a
    # silent, undeclared coupling that only breaks at process-time.
    depends_on_outputs: Dict[str, List[str]] = {}

    # Injected by ForcingConfigRegistry.__init__ after all active configurators
    # are instantiated; lets a configurator check whether a sibling is active
    # (e.g. ConditionsConfigurator gating its own tides/bgc string-building on
    # self.registry.is_active(...)) without reaching into the sibling itself.
    registry: Optional["ForcingConfigRegistry"] = None

    def __eq__(self, other):
        if not isinstance(other, BaseConfigurator):
            return NotImplemented
        for param in self.output_params:
            other_param = other.get_output_param_object(param.name)
            if str(param.value) != str(other_param.value):
                return False
        return True

    def __getattr__(self, name):
        """
        Allow input params to be accessed as attributes:
        self.date_range -> self.get_input_param("date_range").value
        """
        try:
            param = self.get_input_param(name)
        except KeyError:
            raise AttributeError(
                f"{type(self).__name__} has no attribute '{name}'"
            ) from None
        return param

    def __init__(self, **kwargs):
        # Clone declared params for this instance
        self.input_params = [copy.copy(p) for p in self.__class__.input_params]
        self.output_params = [copy.copy(p) for p in self.__class__.output_params]

        self.validate_args(**kwargs)

        # Bind input values to parameters
        for param in self.input_params:
            param.set_item(kwargs[param.name])

    @classmethod
    def check_output_params_exist(cls):
        assert hasattr(
            cls, "output_params"
        ), f"{cls.__name__} has no output_params defined."

    @classmethod
    def check_input_params_synced(cls):
        """Make sure the init args exactly match the input param names. This check is only run in testing"""
        sig = inspect.signature(cls.__init__)
        params = sig.parameters

        init_args = {name for name in params if name != "self"}

        input_param_names = {p.name for p in cls.input_params}

        missing = input_param_names - init_args
        extra = init_args - input_param_names

        assert not (missing), (
            f"{cls.__name__} init/input mismatch:\n"
            f"  Missing init args for input_params: {sorted(missing)}\n"
            f"  Extra init args not declared as input_params (which is okay and won't fail): {sorted(extra)}"
        )

    def validate_args(self, **kwargs):
        """Validate provided inputs against declared input_params."""
        expected = {p.name for p in self.input_params}
        provided = set(kwargs.keys())

        missing = expected - provided
        extra = provided - expected

        if missing:
            raise ValueError(f"Missing required inputs: {missing}")
        if extra:
            raise ValueError(f"Unexpected inputs: {extra}")

    @property
    def is_non_local(self) -> bool:
        """Whether this configurator's case is non-local (CIME's `--non-local`).

        Sourced from the live Case via the registry rather than a declared
        input param, so an XMLConfigParam output doesn't require its
        configurator to accept/thread a `case_is_non_local` ctor arg just to
        reach `apply()` -- it's always False when there's no live Case
        (e.g. direct construction in tests, or deserialize()).
        """
        case = getattr(self.registry, "case", None)
        return bool(getattr(case, "is_non_local", False))

    @abstractmethod
    def configure(self):
        """Bind input values to parameters and files."""
        # A configurator's user_nl parameters go into one CrocoDash block per
        # file, which the next configure_forcings() call replaces (see
        # user_nl_blocks). Consecutive parameters with the same comment share
        # one comment line.
        groups = {}
        for p in self.output_params:
            if isinstance(p, XMLConfigParam):
                p.is_non_local = self.is_non_local
            if isinstance(p, UserNLConfigParam):
                file_groups = groups.setdefault(p.user_nl_name, [])
                if file_groups and file_groups[-1][0] == p.comment:
                    file_groups[-1][1].append(p.pair())
                else:
                    file_groups.append((p.comment, [p.pair()]))
            else:
                p.apply()
        for user_nl_name, file_groups in groups.items():
            user_nl_blocks.write(self.name, user_nl_name, file_groups)
        for p in self.output_params:
            if isinstance(p, UserNLConfigParam):
                p.executed = True

    def stale_outputs(self, previous_config, current_config, inputdir):
        """Files an earlier process step left that the current configuration
        must not reuse, for configure_forcings() to remove.

        previous_config/current_config are the whole config.json contents from
        the earlier configure_forcings() call ({} if there is no record) and
        from this one, since a process step can read a sibling's entry (the
        conditions dates, say). Only a process step that skips outputs it
        finds on disk needs to override this; every other one rewrites its
        files anyway.
        """
        return []

    @classmethod
    def inspect(cls, caseroot):
        """Return an instance of the configurator with placeholder values for input and correct output params from case"""

        placeholder_args = {}
        for param in cls.input_params:
            placeholder_args[param.name] = f""
        obj = cls(**placeholder_args)
        for param in obj.output_params:
            param.inspect(caseroot)
        return obj

    @classmethod
    def deserialize(cls, data: Dict[str, Any]):
        """Rebuild a configurator from its config.json entry.

        Tolerates entries an older or newer CrocoDash wrote: an input missing
        from the entry takes its constructor default, an output missing from
        it stays None, and keys the class no longer declares are ignored. A
        missing input with no default, or an entry the constructor rejects,
        raises ReconfigureRequired.
        """
        inputs, outputs = data.get("inputs", {}), data.get("outputs", {})
        defaults = inspect.signature(cls.__init__).parameters
        input_kwargs = {}
        for param in cls.input_params:
            if param.name in inputs:
                input_kwargs[param.name] = inputs[param.name]
            elif (
                param.name not in defaults
                or defaults[param.name].default is inspect.Parameter.empty
            ):
                raise ReconfigureRequired(
                    f"config.json's '{cls.name.lower()}' entry has no "
                    f"'{param.name}', which this version of CrocoDash requires. "
                    "Rerun configure_forcings() to rewrite config.json."
                )

        try:
            obj = cls(**input_kwargs)
        except ValueError as e:
            raise ReconfigureRequired(
                f"config.json's '{cls.name.lower()}' entry is no longer valid ({e}). "
                "Rerun configure_forcings() to rewrite config.json."
            ) from e
        for param in cls.output_params:
            if param.name in outputs:
                obj.set_output_param(param.name, outputs[param.name])
        return obj

    @classmethod
    def param_specs(cls, required: bool, inputs: Dict[str, Any]) -> List[ParamSpec]:
        """A ParamSpec for each input a user gives this configurator: all but
        the derived ones and the case_* ones the Case fills in.

        required: whether the compset requires this configurator. inputs: its
        entry's inputs in a config.json ({} for none), which are then the
        defaults.
        """
        signature = inspect.signature(cls.__init__).parameters
        params = [
            p for p in cls.input_params if not (p.derived or p.name.startswith("case_"))
        ]
        values = {}
        for param in params:
            default = signature[param.name].default
            if default is inspect.Parameter.empty:
                default = None
            values[param.name] = inputs.get(param.name, default)
        return [
            ParamSpec(
                name=param.name,
                configurator=cls.name,
                required=required
                and signature[param.name].default is inspect.Parameter.empty,
                default=copy.deepcopy(values[param.name]),
                comment=param.comment,
                is_path=isinstance(param, InputFileParam),
                choices=param.choices(values) if param.choices else None,
            )
            for param in params
        ]

    def make_serializable(self, obj):
        if isinstance(obj, Path):
            return str(obj)
        return obj

    def serialize(self) -> Dict[str, Any]:
        """This configurator's config.json entry. A value JSON can't hold
        raises TypeError here, naming its param."""
        output_dict = {"name": self.name, "inputs": {}, "outputs": {}}
        for key, params in (
            ("inputs", self.input_params),
            ("outputs", self.output_params),
        ):
            for param in params:
                value = self.make_serializable(param.value)
                try:
                    json.dumps(value)
                except (TypeError, ValueError) as e:
                    raise TypeError(
                        f"{self.name}'s {param.name} ({value!r}) can't be "
                        f"written to config.json: {e}"
                    ) from None
                output_dict[key][param.name] = value
        return output_dict

    def get_input_param(self, name: str) -> Any:
        return self.get_input_param_object(name).value

    def get_input_param_object(self, name: str) -> InputParam:
        try:
            return next(p for p in self.input_params if p.name == name)
        except StopIteration:
            raise UndeclaredParamError(f"Input param '{name}' not found")

    def get_output_param(self, name: str) -> Any:
        return self.get_output_param_object(name).value

    def get_output_param_object(self, name: str) -> OutputParam:
        try:
            return next(p for p in self.output_params if p.name == name)
        except StopIteration:
            raise UndeclaredParamError(f"Output param '{name}' not found")

    def set_output_param(self, name: str, value):
        self.get_output_param_object(name).set_item(value)

    def set_input_param(self, name: str, value):
        self.get_input_param_object(name).set_item(value)

    # ---- compset logic ----

    @classmethod
    def is_required(cls, compset: str) -> bool:
        return any(sub in compset for sub in cls.required_for_compsets)

    @classmethod
    def validate_compset_compatibility(cls, compset: str) -> bool:
        return all(sub in compset for sub in cls.allowed_compsets) and all(
            sub not in compset for sub in cls.forbidden_compsets
        )

    def get_output_filepaths(self, ocn_ice_directory):
        """Get output files from the output parameters"""
        potential_output_paths = []
        for output in self.output_params:
            if output.is_file:
                potential_file_path = Path(ocn_ice_directory) / str(output.value)
                if potential_file_path.exists():
                    potential_output_paths.append(potential_file_path)
        return potential_output_paths

    def validate_output_filepaths(self, ocn_ice_directory):
        output_paths = self.get_output_filepaths(ocn_ice_directory)
        for path in output_paths:
            if not Path(path).exists():
                return False
        return True
