class ProductRegistry:
    """Static registry that tracks all products and provides driver-like introspection."""

    products = {}  # product_name → class

    @classmethod
    def register(cls, product_cls):
        """Register a product class."""
        cls.products[product_cls.product_name.lower()] = product_cls

    @classmethod
    def list_products(cls):
        return list(cls.products.keys())

    @classmethod
    def product_exists(cls,name):
        return name.lower() in cls.products
    
    @classmethod
    def product_is_of_type(cls,name, the_class):
        return issubclass(cls.products[name.lower()],the_class)

    @classmethod
    def get_product(cls, name):
        return cls.products[name.lower()]

    @classmethod
    def list_access_methods(cls, name):
        product = cls.get_product(name)
        return list(product._access_methods.keys())

    @classmethod
    def get_function(cls, product_name, method_name):
        product = cls.get_product(product_name)
        method = product._access_methods[method_name]
        return method(product)
