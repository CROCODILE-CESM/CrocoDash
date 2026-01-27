# Accessing Raw Data

CrocoDash uses several datasets to setup the model. Data can be gathered directly from public datasources (including the CESM inputdata svn repository) or through helper functions in the CrocoDash Raw Data Access module. The Raw Data Access Module is an expandible, verifyable, object-oriented module with access functions to raw datasets used in CrocoDash. This document explains what it is and what you can do to add more to it, if you would like to!

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


## Want to add more? 

Interested in adding your own spin on a dataset? Maybe with alternative metadata? Check our our additional docs: [Adding Raw Data Products](../for_developers/adding_data_access.md)