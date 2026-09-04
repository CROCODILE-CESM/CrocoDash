"""
Raw Data Access Module Requirements:
1. Must enforce a certain amount of metadata for each product (things like z coordinate name, u velocity name, etc) (from the parent class)
2. Must enforce specific keyword args in each access function (from the parent class)
3. There must be some sort of registry that can list/query all products & access methods
4. As minimal overhead as possible (for me, that meant no initialization!)
5. Should be easy to validate the function (easy to test if they work and the metadata)
6. Should be easy to validate the metadata
7. Need to be able to print out the available products, functions, and their respective descriptions.

How it was solved:
1. There is a set of "abstract" classes that specify an array of "required_metadata". There is no type enforcement currently. This is checked in the _init_subclass hook.
2. There is a set of "abstract" classes that specify an array of "required_args". There is no type enforcement. This is checked in the _init_subclass hook.
3. There is a class called ProductRegistry in the registry.py file that does this
4. The classes are all static.
5. There is a validate method in the BaseProduct class that takes in additional default args from child classes, and the _init_subclass hook validates the args.
6. The metadata is validated in the _init_subclass hook
7. The ProductRegistry holds all of that.
"""

from CrocoDash.raw_data_access.registry import ProductRegistry
import dataclasses
from dataclasses import dataclass
import inspect
import json
from CrocoDash.logging import setup_logger
import tempfile
import shutil


@dataclass(frozen=True)
class Calendar:
    """Pairs the calendar name each downstream consumer expects, so a product can't declare one without the others.

    cf is for xarray's own time decode/encode while reading raw data (its CF
    convention name, e.g. "standard" for the real-world calendar).
    cesm is the CESM xml value.
    mom6 (FMS) is the string the netcdf files must have on time:calendar attribute, since it is not necessarily the same as cf OR cesm.
    """

    cf: str
    cesm: str
    mom6: str

    @classmethod
    def from_config(cls, section: dict) -> "Calendar":
        """Rebuild a Calendar from the ``calendar`` object in a config.json section.

        Reads the copy the chl / river-nutrients configurators store in their
        own ``inputs`` block, so the extraction driver can hand those writers
        the whole Calendar rather than one name and a guess about which of its
        roles that name was meant for. The product metadata block is a separate
        copy, written by BaseProduct.write_metadata and read directly by the
        OBC step; it does not come through here.
        """
        return cls(**section["calendar"])


GREGORIAN = Calendar(cf="standard", cesm="GREGORIAN", mom6="gregorian")
NOLEAP = Calendar(cf="noleap", cesm="NO_LEAP", mom6="noleap")


def accessmethod(func=None, *, description=None, type=None, how_to_use=None):
    def decorator(f):
        f = staticmethod(f)
        f._is_access_method = True
        f._description = description
        f._type = type
        f._how_to_use = how_to_use
        return f

    # Case 1: decorator used WITHOUT args: @accessmethod
    if callable(func):
        return decorator(func)

    # Case 2: decorator used WITH args: @accessmethod(description="foo")
    return decorator


class BaseProduct:
    """Base class for all raw data products. It enforces the metadata on the product as well as the function args."""

    # Subclasses must define this
    required_metadata = ["product_name", "description", "link"]
    required_args = ["output_folder", "output_filename"]

    _access_methods = {}  # method_name → {func}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # Only register concrete classes - i.e. how we make all these base classes "abstract" (Not actually abstract because we're not trying to enforce methods in child classes, just attributes)
        if not getattr(cls, "product_name", None):
            cls._is_abstract = True
            return
        else:
            cls._is_abstract = False

        # Assign a logger for each subclass
        cls.logger = setup_logger(cls.__name__)

        cls._access_methods = {}
        for name, attr in cls.__dict__.items():
            if isinstance(attr, staticmethod) and getattr(
                attr, "_is_access_method", False
            ):
                cls._access_methods[name] = attr
        # ---- Validate metadata ----
        for field in cls.required_metadata:
            if not hasattr(cls, field):
                raise ValueError(f"{cls.__name__} missing required metadata: {field}")

        # ---- Validate access methods ----
        for name, entry in cls._access_methods.items():
            func = entry.__func__
            sig = inspect.signature(func)

            # All required args must be present
            missing = [arg for arg in cls.required_args if arg not in sig.parameters]
            if missing:
                raise ValueError(
                    f"Access method '{name}' in {cls.product_name} missing args {missing}"
                )

        # ---- Auto-register product ----
        ProductRegistry.register(cls)

    @classmethod
    def validate_call(cls, method_name, **kwargs):
        """Validate that a call to an access method has correct arguments."""
        if method_name not in cls._access_methods:
            raise KeyError(f"{method_name} not found for product {cls.product_name}")

        missing = [arg for arg in cls.required_args if arg not in kwargs]
        if missing:
            raise ValueError(f"{cls.product_name}.{method_name} missing args {missing}")

    # Default validation — can be overridden
    @classmethod
    def validate_method(cls, method_name, **kwargs):
        """Default validation just makes a toy call with a temporary directory."""
        temp_dir = tempfile.mkdtemp()
        default_args = {
            "output_folder": temp_dir,
            "output_filename": "test_file.notreal",
        }
        final_args = {**default_args, **kwargs}
        if method_name not in cls._access_methods:
            raise ValueError(f"{method_name} not in {cls.__name__}")

        func = cls._access_methods[method_name].__func__

        # Default “toy call” signature:
        try:
            return func(**final_args)
        except Exception as e:
            cls.logger.error(
                f"Validation failed for {cls.product_name}.{method_name}: {e}"
            )
            return False
        shutil.rmtree(temp_dir)
        return True

    @classmethod
    def write_metadata(cls, file_path: str = None) -> dict:
        """Return a dict of the class metadata fields and their values, writes a file if a filepath is specified."""

        unset = object()

        def to_json_value(value):
            """Return a JSON-serializable form of `value`, else `unset`.

            Dataclasses (e.g. Calendar) are expanded to a named dict so they
            survive into the metadata instead of being silently dropped. The
            sentinel is not None, because None is itself serializable and a
            class attribute set to None should be kept.
            """
            if dataclasses.is_dataclass(value) and not isinstance(value, type):
                value = dataclasses.asdict(value)
            try:
                json.dumps(value)
                return value
            except (TypeError, OverflowError):
                return unset

        metadata = {}
        for name, value in cls.__dict__.items():
            if name.startswith("_") or isinstance(value, (staticmethod, classmethod)):
                continue
            json_value = to_json_value(value)
            if json_value is not unset:
                metadata[name] = json_value
        if file_path is not None:
            with open(file_path, "w") as f:
                json.dump(metadata, f, indent=2)
        return metadata


class DatedBaseProduct(BaseProduct):
    """Specific enforcement needs for Dated Products"""

    required_args = BaseProduct.required_args + [
        "dates",
    ]

    @classmethod
    def validate_method(cls, method_name, **kwargs):

        # Add child-class defaults
        extra_defaults = {
            "dates": ["2000-01-01", "2000-01-02"],
        }
        final_args = {**extra_defaults, **kwargs}

        # Delegate to the base implementation
        return super().validate_method(method_name, **final_args)


class ForcingProduct(DatedBaseProduct):
    """Generic enforcement for any gridded, bounding-box-downloadable forcing
    product. Holds the metadata every such product needs regardless of
    target model: a lat/lon/variables/dates download contract, sane toy-call
    defaults for that contract's lat/lon args, and its own time-axis naming
    (``time_var_name``/``time_units``/``calendar``) --
    every dated forcing product has *some* time coordinate to name, even one
    (like a static restart snapshot) that leaves these unused. Velocity/
    tracer grid-point metadata is NOT here -- see
    ``VelocityTracerForcingProduct``/``MOM6ForcingProduct``.
    """

    required_args = DatedBaseProduct.required_args + [
        "variables",
        "lon_max",
        "lat_max",
        "lon_min",
        "lat_min",
        "name",
    ]

    required_metadata = DatedBaseProduct.required_metadata + [
        "time_var_name",
        "time_units",
        "calendar",
    ]

    def __init_subclass__(cls, **kwargs):
        # Let BaseProduct classify the subclass first: the abstract
        # intermediates in this hierarchy (VelocityTracerForcingProduct,
        # MOM6ForcingProduct) have no product_name and no reason to declare a
        # Calendar, so only concrete products are held to the check below.
        super().__init_subclass__(**kwargs)
        if cls._is_abstract:
            return

        # One Calendar is the whole calendar contract: the three names it
        # carries cannot disagree. write_metadata expands it into a named
        # dict, so it survives into the product metadata block of config.json
        # rather than being dropped by that method's JSON filter; the OBC
        # step reads calendar.mom6 straight out of it.
        calendar = getattr(cls, "calendar", None)
        assert isinstance(calendar, Calendar), (
            f"{cls.__name__} must declare `calendar` as a Calendar instance "
            f"(got {type(calendar).__name__}); use a module-level constant such "
            "as GREGORIAN or NOLEAP rather than bare calendar-name strings."
        )

    @classmethod
    def validate_method(cls, method_name, **kwargs):

        # Add child-class defaults
        extra_defaults = {
            "lat_min": 30,
            "lat_max": 30.1,
            "lon_min": 30,
            "lon_max": 30.1,
        }

        # Delegate to the base implementation
        return super().validate_method(method_name, **extra_defaults)


class VelocityTracerForcingProduct(ForcingProduct):
    """Coordinate/variable-name metadata for a product's u/v velocity and
    tracer grid points -- the var-map contract consumed by
    ``regional_mom6``'s ``Segment.regrid_velocity_tracers``, not by the
    generic GET layer. Shared by ``MOM6ForcingProduct`` and any future
    model whose velocity/tracer state lives on a plain (nj, ni) index space.
    """

    required_metadata = ForcingProduct.required_metadata + [
        "u_x_coord",
        "u_y_coord",
        "v_x_coord",
        "v_y_coord",
        "tracer_x_coord",
        "tracer_y_coord",
        "u_var_name",
        "v_var_name",
        "tracer_var_names",
        "depth_coord",
    ]


class MOM6ForcingProduct(VelocityTracerForcingProduct):
    """MOM6/regional_mom6-specific regridding metadata on top of
    ``VelocityTracerForcingProduct`` -- SSH and the OBC fill method, neither
    of which generalize to other models. Products that feed CrocoDash's
    MOM6 OBC/IC pipeline (``GLORYS``, ``CESM_POP_OUTPUT``, ``CESM_MOM_OUTPUT``)
    extend this.
    """

    required_metadata = VelocityTracerForcingProduct.required_metadata + [
        "eta_var_name",
        "boundary_fill_method",
    ]

    def __init_subclass__(cls, **kwargs):
        # 1. Let ForcingProduct/BaseProduct do their validation first
        super().__init_subclass__(**kwargs)

        # 2. tracer_var_names must be a dictionary with temp & salt
        assert (
            "temp" in cls.tracer_var_names.keys()
            and "salt" in cls.tracer_var_names.keys()
        ), "keys temp & salt must be in the tracer_var_names variable."

    @classmethod
    def write_metadata(
        cls, file_path: str | None = None, include_marbl_tracers=False
    ) -> dict:
        # 1. Get base metadata
        base = super().write_metadata()

        # 2. Merge marbl_var_names → tracer_var_names

        if include_marbl_tracers and hasattr(cls, "marbl_var_names"):
            merged = dict(base["tracer_var_names"])  # copy existing
            merged.update(cls.marbl_var_names)
            base["tracer_var_names"] = merged
        elif include_marbl_tracers and not hasattr(cls, "marbl_var_names"):
            raise ValueError(
                "This product does not have marbl tracer var names and cannot be written out as such."
            )
        else:
            # BaseProduct.write_metadata copies every public, JSON-compatible
            # class attribute, so a product that merely *declares*
            # marbl_var_names (CESM_POP_OUTPUT does, so a %MARBL-BIO compset can
            # use it) carries the key into the metadata even when BGC is off.
            # The BGC tracers were never merged into tracer_var_names above, so
            # they are never regridded -- but the OBC step reads the presence of
            # this key as "these were regridded" and then fails looking for
            # <tracer>_segment_NNN. Drop it so the key means what the branch
            # above makes it mean.
            base.pop("marbl_var_names", None)

        # 3. Optionally write file
        if file_path is not None:
            with open(file_path, "w") as f:
                json.dump(base, f, indent=2)

        return base
