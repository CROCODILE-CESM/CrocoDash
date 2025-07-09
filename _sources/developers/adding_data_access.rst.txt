Adding Data to the Data Access Module
=======================================


The Data Access Module is where we add methods to access all datasets used in CrocoDash.

To add a new dataset:
    1. Create a new python file named after the product
    2. Add a function that takes in dates, lat & lon min & max, and any other parameters required
    3. Update the tables: data_access_registry with function names and data_product_registry with product name