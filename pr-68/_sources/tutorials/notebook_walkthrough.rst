.. _notebook_walkthrough:

CrocoDash Basic Notebook Walkthrough 
====================================

This document provides a step-by-step walkthrough of the basic CrocoDash demo, showcasing how to use the platform effectively.

Getting Started
------------------

Follow the steps in :ref:`installation` to set up CrocoDash on your local machine. We will be working through the basic demo (demos/gallery/notebooks/tutorials/minimal_demo_rect.ipynb), which is designed to help you familiarize yourself
with the basic steps of using CrocoDash, no additional features. Please open up that demo in the CrocoDash environment to get started.

Basic Demo Overview
----------------------
The basic demo sets up a small rectangular domain around Panama for a few days with GLORYS data (for initial & boundary conditions) and GEBCO bathymetry. The atmospheric forcing is JRA, provided through the CESM.
Check out the demo 
`here <https://crocodile-cesm.github.io/CrocoGallery/notebooks/tutorials/minimal_demo_rect.html>`_.


Section 1: Set up the Domain
------------------------------------------------

Step 1: Set up the horizontal grid
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

Step 2: Set up the bathymetry
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

Step 3: Get the Bathymetry (and any other) Data 
*****************************************************
In this step, we will download the necessary data for the bathymetry. GLORYS data is gathered later on in the workflow & JRA data is provided through the CESM.
The only data required to be gathered in this step is the GEBCO bathymetry data. You can download the GEBCO bathymetry data from the official website:

    https://www.gebco.net/data_and_products/gridded_bathymetry_data/

Download the latest GEBCO gridded bathymetry dataset (NetCDF format is recommended). Once downloaded, place the file somewhere you remember the path for use in the demo.

The other option is to download the data through the CrocoDash raw_data_access module. This module allows you to access and download raw data directly from the CrocoDash platform. To use this feature, checkout the data access feature demo here: 
(demos/gallery/notebooks/features/add_data_products.ipynb)

Step 4: Load the bathymetry data and put it on our Grid
**********************************************************************************
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


Step 5: Edit the topography
*****************************************
In this step, we will load the topo object into an interactive widget we can use to change the depth, erase basins, or change the minimum depth. This can be useful for a few reasons, but is not a required step. 

.. code-block:: python

    %matplotlib ipympl
    from CrocoDash.topo_editor import TopoEditor

    topo.depth["units"] = "m"
    TopoEditor(topo)


Step 6: Generate the Vgrid
*****************************************
In this step, we load the vertical grid, or how many layers of the ocean we have. This example uses some standards of 75 layers and a hyperbolic function.

.. code-block:: python

    from CrocoDash.vgrid import VGrid

    vgrid  = VGrid.hyperbolic(
        nk = 75,
        depth = topo.max_depth,
        ratio=20.0
    )

Section 2: Create the CESM Case
----------------------------------
In this step, we pass in all of the information we generated in our previous steps into our CrocoDash Case module, which sets up a CESM case with all of the information we need for a regional run.
There's lots of parameter changes and additional information that we need to do to make a regional model. 


.. tip:: 
   :class: note

    Don't know what a CESM case is? Go through the CESM tutorial here: https://ncar.github.io/CESM-Tutorial/README.html

Step 1: Set the paths
****************************************************************************
How CrocoDash works is that we have a input directory for all the input data, as well as a case directory, which is the CESM case. So all of these grids will get written to the input directory, 
and all of the parameters get written to the case directory. In our input directory,there's two folders. One folder (default is "glorys") is where all the raw forcing data is generated, and the other 
folder is called "ocnice" where all of the grids go. This step here, defines all the paths for these directories, as well as where is the CESM!


.. code-block:: python

    # CESM case (experiment) name
    casename = "panama-1"

    # CESM source root (Update this path accordingly!!!)
    cesmroot ="/Users/manishrv/CrocoGallery/cesm"

    # Place where all your input files go 
    inputdir = Path.home() / "croc_input" / casename
        
    # CESM case directory
    caseroot = Path.home() / "croc_cases" / casename
    

Step 2: Pass all information in
****************************************************************************
Here, we pass in all the previously generated information. Pass in your own project code to charge for the CESM, and set the machine attribute to the machine you want to run the CESM on. 


.. code-block:: python

    from CrocoDash.case import Case

    case = Case(
        cesmroot = cesmroot,
        caseroot = caseroot,
        inputdir = inputdir,
        ocn_grid = grid,
        ocn_vgrid = vgrid,
        ocn_topo = topo,
        project = 'NCGD0011',
        override = True,
        machine = "ubuntu-latest"
    )

.. caution:: 

    Setting override to True will DELETE the previous case at the caseroot and inputdir. Don't set this to true if you don't want that behavior!

Section 3: Generate data and configure case to specifications
----------------------------------------------------------------
In these last two steps, the user gets to specify all options they would like in their regional case. We then generate all the required data for the case needed, which means initial & boundary conditions


Step 1: Configure Forcings
******************************
In this step, the user gets to add the time dependence, and any other options/specifications they want in their case, like chlorophyll, tides, non-default data products, etc... This is where a lot of the functionality of CrocoDash 
is, so there are several feature demos in the CrocoGallery to showcase the different parameters of this function for options in your regional case. You can check out all the parameters possible 
in the api docs: :ref:`CrocoDash`

In this example, we have no 
additional specifications, and only add the time dependence and the function_name we would like to use to generate the raw data for the initial and boundary conditions. The function_name parameter is explained in further detail in the add data products notebook, so will not be covered here.
It simply downloads the data through the notebook instead of offering a script for the user to use in their terminal, which is the default. 

Please run the lines below. This step lets us (and the model) know we are running the model for 9 days in 2020.

.. code-block:: python

    case.configure_forcings(
    date_range = ["2020-01-01 00:00:00", "2020-01-09 00:00:00"],
    function_name="get_glorys_data_from_cds_api"
    )

Running configure_forcings will then output information on what it did *and* any additional steps needed (based on specifications). Please follow those steps as needed. In this example, we won't have any additional steps, but it's important to read that or the model won't work!

Step 2: Process Forcings
******************************
In this final step, given the information passed in configure_forcings, we process all of that information to generate all the required data. 

Please run the lines below. This step will likely take the longest time.

.. code-block:: python

    case.process_forcings()


.. tip::
   :class: note

    You can turn off steps of the process_forcings, like generating the initial condition, by setting process_initial_condition=False. This can be helpful if you have already processed     the data and just need to 
    reprocess some of it! An exmaple of this would be to expand the model to run for more time. The only processing we need increased is the boundary conditions. You don't need to run the initial condition again! 

Section 3: Build & Run the Model!
-----------------------------------
That's it! You can now go to the case directory and build and run the model! It's useful to poke around and see what changes were made by CrocoDash to be able to run the model. Check out user_nl_mom for all the parameter changes.

.. code-block:: bash

    cd ~/croc_input/panama-1
    ./case.build
    ./case.submit