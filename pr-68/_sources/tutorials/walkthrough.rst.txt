.. _walkthrough:

CrocoDash Basic Demo Walkthrough 
====================================

This document provides a step-by-step walkthrough of the basic CrocoDash demo, showcasing how to use the platform effectively.

Getting Started
------------------

Follow the steps in _ref:`installation` to set up CrocoDash on your local machine. We will be working through the basic demo (demos/gallery/notebooks/tutorials/minimal_demo_rect.ipynb), which is designed to help you familiarize yourself
 with the basic steps of using CrocoDash, no additional features. Please open up that demo in the CrocoDash environment to get started.

Basic Demo Overview
----------------------
The basic demo sets up a small rectangular domain around Panama for a few days with GLORYS data (for initial & boundary conditions) and GEBCO bathymetry. The atmospheric forcing is JRA, provided through the CESM


Step 1: Set up the Domain
------------------------------------------------

Step 1.1: Set up the horizontal grid
*****************************************
In this step, we will set up a small rectangular domain around Panama. The domain is defined by its latitude and longitude bounds. The grid used here is defined by specifying a corner point and 
 the the length of the rectangle edges, as well as specifying the resolution. Please run this cell:

.. code-block:: python

    from CrocoDash.grid import Grid

    grid = Grid(
        resolution = 0.01,
        xstart = 278.0,
        lenx = 1.0,
        ystart = 7.0,
        leny = 1.0,
        name = "panama1",
    )

Step 1.2: Set up the bathymetry
*****************************************
In this step, we have to use the grid and tell the model what the ocean actually looks like, the bathymetry. The bathymetry is defined by a NetCDF file that contains the depth values for each grid point.
To set up the bathymetry, we will use the GEBCO bathymetry data that we download in the next step. This step just sets up the bathymetry object, which we will pass into the model later on. Minimum depth
is used to set the minimum depth of the ocean, any shallower becomes land.

.. code-block:: python

    from CrocoDash.topo import Topo

    topo = Topo(
        grid = grid,
        min_depth = 9.5,
    )

Step 1.3: Get the Bathymetry (and any other) Data 
--------------------------------------------------------
In this step, we will download the necessary data for the bathymetry. GLORYS data is gathered later on in the workflow & JRA data is provided through the CESM.
The only data required to be gathered in this step is the GEBCO bathymetry data. You can download the GEBCO bathymetry data from the official website:

    https://www.gebco.net/data_and_products/gridded_bathymetry_data/

Download the latest GEBCO gridded bathymetry dataset (NetCDF format is recommended). Once downloaded, place the file somewhere you remember the path for use in the demo.

The other option is to download the data through the CrocoDash raw_data_access module. This module allows you to access and download raw data directly from the CrocoDash platform. To use this feature, checkout the data access feature demo here: 
(demos/gallery/notebooks/features/add_data_products.ipynb)

Step 1.4: Load the bathymetry data and put it on our Grid
--------------------------------------------------------------
In this step, we will load the GEBCO bathymetry data that we downloaded in the previous step and put it on our grid. This is done by using the `Topo` class that we created in the previous step. 
The `Topo` class has a method called `interpolate_from_file` that takes the path to the bathymetry file and loads it onto the grid.


.. code-block:: python

    bathymetry_path='<PATH_TO_BATHYMETRY>'

    topo.interpolate_from_file(
        file_path = bathymetry_path,
        longitude_coordinate_name="lon",
        latitude_coordinate_name="lat",
        vertical_coordinate_name="elevation"
    )
