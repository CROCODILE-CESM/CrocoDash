import inspect

from CrocoDash.raw_data_access.datasets import load_all_datasets


class ProductRegistry:
    """Static registry that tracks all products and provides driver-like introspection."""

    loaded = False
    products = {}  # product_name → class

    @classmethod
    def register(cls, product_cls):
        """Register a product class."""
        cls.products[product_cls.product_name.lower()] = product_cls

    @classmethod
    def list_products(cls):
        return list(cls.products.keys())

    @classmethod
    def product_exists(cls, name):
        return name.lower() in cls.products

    @classmethod
    def product_is_of_type(cls, name, the_class):
        return issubclass(cls.products[name.lower()], the_class)

    @classmethod
    def get_product(cls, name):
        return cls.products[name.lower()]

    @classmethod
    def list_access_methods(cls, name):
        product = cls.get_product(name)
        return list(product._access_methods.keys())

    @classmethod
    def get_access_function(cls, product_name, method_name):
        """Return the raw function (unbound), even if staticmethod."""
        product = cls.get_product(product_name)
        func = product._access_methods[method_name]

        return func

    @classmethod
    def validate_function(cls, product_name, method_name):
        product = cls.get_product(product_name)
        return product.validate_method(method_name)

    @classmethod
    def call(cls, product_name, method_name, **kwargs):
        product = cls.get_product(product_name)
        product.validate_call(method_name, **kwargs)
        method = product._access_methods[method_name]
        return method(**kwargs)

    @classmethod
    def get_function_default_args(cls, product_name, function_name):
        """Return a dict of {param: default} for all non-required parameters of an access method."""
        product = cls.get_product(product_name)
        func = product._access_methods[function_name].__func__
        sig = inspect.signature(func)
        required = set(product.required_args)
        return {
            name: param.default
            for name, param in sig.parameters.items()
            if name not in required and param.default is not inspect.Parameter.empty
        }

    @classmethod
    def load(cls):
        loaded = True
        load_all_datasets()
