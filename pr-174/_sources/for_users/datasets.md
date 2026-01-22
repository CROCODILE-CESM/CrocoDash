# Accessing Raw Data

CrocoDash uses several datasets to setup the model. Data can be gathered directly from public datasources (including the CESM inputdata svn repository) or through helper functions in the CrocoDash data_access module.

Specific datasets can either be accessed directly through the data access module or be chosen by adding arguments to the case.configure_forcings function. Check out the demo
[here](https://crocodile-cesm.github.io/CrocoGallery/latest/notebooks/features/add-data-products/).


Users can check if datasets are accessible at this [link](https://crocodile-cesm.github.io/CrocoDash/reports/raw_data_status.html).

Please see below for available datasets.

```{eval-rst}
.. csv-table:: Data Product Registry
   :file: ../raw_data_access/products.csv
   :header-rows: 1


```

## CrocoDash Data Access Module

CrocoDash has a data_access module for accessing various datasets. Please see below for a table of available methods.

```{eval-rst}
.. csv-table:: Data Access Registry
   :file: ../raw_data_access/functions.csv
   :header-rows: 1

```


