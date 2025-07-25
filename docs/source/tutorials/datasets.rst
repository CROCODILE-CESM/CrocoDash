Datasets
============

CrocoDash uses several datasets to setup the model. Data can be gathered directly from public datasources (including the CESM inputdata svn repository) or through helper functions in the CrocoDash data_access module. 
Users can check if datasets are accessible at this `link <https://crocodile-cesm.github.io/CrocoDash/reports/raw_data_status.html>`_.

Please see below for available datasets.

.. csv-table:: Data Product Registry
   :file: ../../../CrocoDash/raw_data_access/config/data_product_registry.csv
   :header-rows: 1



CrocoDash Data Access Module
#############################
CrocoDash has a data_access module for accessing various datasets. Please see below for a table of available methods.

.. csv-table:: Data Access Registry
   :file: ../../../CrocoDash/raw_data_access/config/data_access_registry.csv
   :header-rows: 1


Specific datasets can be chosen by adding arguments to the case.configure_forcings function. Check out the demo 
`here <https://crocodile-cesm.github.io/CrocoGallery/notebooks/features/add_data_products.html>`_.

Public (Raw) Data Access
#########################

Users can directly download data from the following public sources.

CESM Input Data Global Grid & Bathymetry
-------------------------------------------

If users would prefer to subset a global grid, they can find one set of bathymetry and grid at the svn repo under the sub heading 'tx1_12v1'

GEBCO Dataset
------------------------

Users can find GEBCO data available publicly at https://www.gebco.net/data_and_products/gridded_bathymetry_data/,  through the GEBCO dashboard https://download.gebco.net/, or can access GEBCO through the CrocoDash data access module (To be developed).

GLORYS Dataset
---------------------------------

Users can find GLORYS data available publicly at https://data.marine.copernicus.eu/product/GLOBAL_MULTIYEAR_PHY_001_030/description,  through the GLORYS dashboard https://data.marine.copernicus.eu/product/GLOBAL_MULTIYEAR_PHY_001_030/download, or can access GLORYS through the CrocoDash data access module.

TPXO Tide Model Dataset
------------------------

Users can request TPXO data available for non-commercial use at https://www.tpxo.net/global. The global data only needs to be gathered one time, and is not required to setup a regional case.