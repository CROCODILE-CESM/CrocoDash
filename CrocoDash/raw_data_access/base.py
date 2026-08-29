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
2b. Args the framework does NOT pass unconditionally (currently just ``freq``) live in "required_tunable_args" instead, which additionally checks that the arg carries a default -- see BaseProduct.required_tunable_args.
3. There is a class called ProductRegistry in the registry.py file that does this
4. The classes are all static.
5. There is a validate method in the BaseProduct class that takes in additional default args from child classes, and the _init_subclass hook validates the args.
6. The metadata is validated in the _init_subclass hook
7. The ProductRegistry holds all of that.
"""

from CrocoDash.raw_data_access.registry import ProductRegistry
from dataclasses import dataclass
import inspect
import json
import pandas as pd
from CrocoDash.logging import setup_logger
import tempfile
import shutil


@dataclass(frozen=True)
class Calendar:
    """Pairs the calendar name each downstream consumer expects, so a product can't declare one without the others.

    cf is for xarray's own time decode/encode while reading raw data (its CF
    convention name, e.g. "standard" for the real-world calendar). cesm is
    the CIME CALENDAR xml value. mom6 is the literal string the regridding
    step must stamp on output forcing files' time:calendar attribute, since
    MOM6's get_cal_time() accepts neither cf's "standard" nor cesm's
    upper-cased "GREGORIAN"/"NO_LEAP" -- only e.g. "gregorian"/"noleap".
    """

    cf: str
    cesm: str
    mom6: str


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


def frequency_step(freq: str) -> pd.Timedelta:
    """Approximate wall-clock spacing of a pandas frequency alias, as a Timedelta.

    Used only to order two frequencies coarsest-first, so an approximation is
    fine and a fixed-length one is unavailable anyway: calendar offsets like
    "MS" (month start) have no constant duration, so ``pd.tseries.frequencies.
    to_offset("MS").nanos`` raises. Measuring the mean spacing over a year of
    generated stamps handles every alias uniformly -- fixed ("D", "6h") and
    calendar ("MS", "QS", "YS", "W") alike.
    """
    try:
        idx = pd.date_range("2001-01-01", periods=13, freq=freq)
    except ValueError as e:
        raise ValueError(f"{freq!r} is not a valid pandas frequency alias: {e}") from e
    return (idx[-1] - idx[0]) / (len(idx) - 1)


def resolve_frequency(product, freq: str | None) -> str:
    """Return the frequency an access method should actually sample at.

    ``freq=None`` means "whatever the product natively provides", which keeps
    every existing call site behaving exactly as before. A coarser request is
    honoured; a finer one is rejected, because no access method can invent
    records the archive does not contain -- left unchecked it would silently
    return fewer timestamps than asked for.

    Products whose cadence is a property of the archive the *user* points at
    rather than of the product itself (the CESM tseries readers, whose
    dataset_path may be month_1, day_1, ...) declare
    ``native_frequency = None``; nothing can be validated statically for those,
    so the request is passed through untouched.
    """
    native = product.native_frequency
    if freq is None:
        return native
    if native is None:
        return freq
    if frequency_step(freq) < frequency_step(native):
        raise ValueError(
            f"{product.product_name} is {native} data; freq={freq!r} is finer than "
            f"that, so sampling at it would silently yield fewer records than "
            f"requested. Pass freq={native!r} or coarser."
        )
    return freq


def require_native_frequency(product, freq: str | None, method_name: str, hint: str):
    """Reject a non-native ``freq`` for an access method that cannot honour one.

    Every dated access method must accept ``freq`` so that a single
    ``function_overrides={"freq": ...}`` is valid no matter which method the
    user selects. Methods that fetch by date *range* (a server-side query, a
    generated script, a file-window overlap scan) have no way to sample within
    it, so they say so loudly here instead of accepting the argument and
    quietly ignoring it.
    """
    if freq is None or freq == product.native_frequency:
        return
    raise NotImplementedError(
        f"{product.product_name}.{method_name} cannot sub-sample: {hint} "
        f"Drop freq (or pass freq={product.native_frequency!r})."
    )


class BaseProduct:
    """Base class for all raw data products. It enforces the metadata on the product as well as the function args."""

    # Subclasses must define this
    required_metadata = ["product_name", "description", "link"]
    required_args = ["output_folder", "output_filename"]
    # Args every access method must accept but that the framework does not pass
    # unconditionally, so they must additionally carry a default. Kept separate
    # from required_args: an arg in there may legitimately be positional, while
    # one in here is broken if it is (the framework would omit it and the call
    # would raise TypeError).
    required_tunable_args = []

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

            # Tunable args must be present AND optional
            for arg in cls.required_tunable_args:
                param = sig.parameters.get(arg)
                if param is None:
                    raise ValueError(
                        f"Access method '{name}' in {cls.product_name} missing "
                        f"tunable arg '{arg}'"
                    )
                if param.default is inspect._empty:
                    raise ValueError(
                        f"Access method '{name}' in {cls.product_name} declares "
                        f"'{arg}' without a default. Tunable args must be optional: "
                        f"the framework only passes them when the user overrides "
                        f"them, so a required one raises TypeError on every "
                        f"ordinary call."
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

        def is_json_compatible(value):
            try:
                json.dumps(value)
                return True
            except (TypeError, OverflowError):
                return False

        metadata = {}
        for name, value in cls.__dict__.items():
            if (
                not name.startswith("_")
                and not isinstance(value, (staticmethod, classmethod))
                and is_json_compatible(value)
            ):
                metadata[name] = value
        if file_path is not None:
            with open(file_path, "w") as f:
                json.dump(metadata, f, indent=2)
        return metadata


class DatedBaseProduct(BaseProduct):
    """Specific enforcement needs for Dated Products.

    Every dated product declares its own cadence (``native_frequency``) and
    every one of its access methods accepts ``freq``, so a caller can ask for a
    coarser sampling of a date range without knowing which product or access
    method is behind it. A year of daily GLORYS is 369 files to open; the same
    year at freq="MS" is 13.

    ``native_frequency`` is a pandas frequency alias ("D", "MS", "6h", ...), or
    None for products whose cadence is a property of the archive the user points
    at rather than of the product itself -- see resolve_frequency.
    """

    required_metadata = BaseProduct.required_metadata + [
        "native_frequency",
    ]
    required_args = BaseProduct.required_args + [
        "dates",
    ]
    required_tunable_args = BaseProduct.required_tunable_args + [
        "freq",
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
    (``time_var_name``/``time_units``/``cf_calendar``/``cesm_calendar``/``mom6_calendar``) --
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
        "cf_calendar",
        "cesm_calendar",
        "mom6_calendar",
    ]

    def __init_subclass__(cls, **kwargs):
        # Derive cf_calendar/cesm_calendar/mom6_calendar from a single `calendar` attr, if declared
        calendar = getattr(cls, "calendar", None)
        if calendar is not None:
            cls.cf_calendar = calendar.cf
            cls.cesm_calendar = calendar.cesm
            cls.mom6_calendar = calendar.mom6

        super().__init_subclass__(**kwargs)

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
        merged = dict(base["tracer_var_names"])  # copy existing
        if include_marbl_tracers and hasattr(cls, "marbl_var_names"):
            merged.update(cls.marbl_var_names)
            base["tracer_var_names"] = merged
            # Keep the MARBL subset addressable on its own. Once merged above,
            # the BGC tracers are indistinguishable from temp/salt, and the OBC
            # step needs to know which ones to split into per-tracer files.
            base["marbl_var_names"] = dict(cls.marbl_var_names)
        elif include_marbl_tracers and not hasattr(cls, "marbl_var_names"):
            raise ValueError(
                "This product does not have marbl tracer var names and cannot be written out as such."
            )

        # 3. Optionally write file
        if file_path is not None:
            with open(file_path, "w") as f:
                json.dump(base, f, indent=2)

        return base
