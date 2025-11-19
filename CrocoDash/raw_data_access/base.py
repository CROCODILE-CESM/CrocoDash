# raw_data_access/base.py

from .registry import ProductRegistry
import inspect
import json
from ..utils import setup_logger


def accessmethod(func=None, *, description=None, type=None):
    def decorator(f):
        f._is_access_method = True
        f._description = description
        f._dtype = type
        return f

    # Case 1: decorator used WITHOUT args: @accessmethod
    if callable(func):
        return decorator(func)

    # Case 2: decorator used WITH args: @accessmethod(description="foo")
    return decorator


class BaseProduct:
    """Base class for all raw data products. It enforces the metadata on the product as well as the function args."""

    # Subclasses must define this
    required_metadata = ["product_name", "description"]
    required_args = ["output_folder", "output_filename"]

    _access_methods = {}  # method_name → {func}

    def __init_subclass__(cls, **kwargs):

        super().__init_subclass__(**kwargs)

        # Skip validation for intermediate base classes
        if getattr(cls, "_is_abstract_base", False):
            return

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


class ForcingProduct(BaseProduct):
    """Specific enforcement needs for Forcing Products"""

    _is_abstract_base = True  # <- tells BaseProduct to skip validation

    required_metadata = BaseProduct.required_metadata + [
        "time_var_name",
        "u_x_coord",
        "u_y_coord",
        "v_x_coord",
        "v_y_coord",
        "tracer_x_coord",
        "tracer_y_coord",
        "depth_coord",
        "u_var_name",
        "v_var_name",
        "eta_var_name",
        "tracer_var_names",
        "boundary_fill_method",
        "time_units",
    ]

    required_args = BaseProduct.required_args + [
        "dates",
        "variables",
        "lon_max",
        "lat_max",
        "lon_min",
        "lat_min",
    ]

    def __init_subclass__(cls, **kwargs):

        # Concrete subclasses should not have the abstract flag
        cls._is_abstract_base = False

        # 1. Let BaseProduct do its validation first
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
        if hasattr(cls, "marbl_var_names"):
            merged.update(cls.marbl_var_names)
            base["tracer_var_names"] = merged
        else:
            raise ValueError(
                "This product does not have marbl tracer var names and cannot be written out as such."
            )

        # 3. Optionally write file
        if file_path is not None:
            with open(file_path, "w") as f:
                json.dump(base, f, indent=2)

        return base
