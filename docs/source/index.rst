.. CrocoDash Documentation master file, created by
   sphinx-quickstart on Fri Oct 18 11:22:10 2024.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to the CrocoDash Documentation!
========================================

CrocoDash is a Python package designed to setup regional Modular Ocean Model 6 (MOM6) cases within the Community Earth System Model (CESM). 
CrocoDash takes advantage and integrates several MOM6 and CESM tools into an unified workflow for regional MOM6 case configuration.
CrocoDash is part of the CROCODILE project. Please see the `project description <https://github.com/CROCODILE-CESM>`_  for scientific motivation.

Description
----------------
CrocoDash brings regional MOM6 inside the CESM. It is a lightweight package that ties together each part of the MOM6 in CESM setup process into one package.

1. Grid Generation (Through `mom6_bathy <https://github.com/NCAR/mom6_bathy>`_ and `regional-mom6 <https://github.com/CROCODILE-CESM/regional-mom6>`_)
2. CESM Setup (Through `VisualCaseGen <https://github.com/CROCODILE-CESM/VisualCaseGen>`_)
3. Forcing + OBC Setup (Through `CESM <https://github.com/CROCODILE-CESM/CESM>`_ & `regional-mom6 <https://github.com/CROCODILE-CESM/regional-mom6>`_)

CrocoDash also provides a variety of helper tools to help setup a case, for example, a tool to edit bathymetry (TopoEditor) or a tool to download public datasets simply (raw_data_access module). 

Get Started 
-------------

1. Please see the :ref:`installation` page.
2. Walk through our `tutorials <https://crocodile-cesm.github.io/CrocoGallery/>`_ for an easy introduction
3. Check out our `gallery of demos <hhttps://crocodile-cesm.github.io/CrocoGallery/notebooks/use_cases/index.html>`_ for more use cases and cool features.


.. toctree::
   :maxdepth: 1
   :caption: Contents:

   installation
   Tutorials & Gallery <https://crocodile-cesm.github.io/CrocoGallery/>
   datasets
   structure
   configure_forcings
   additional_resources
   developers/index
   api-docs/modules
   Common Errors <https://github.com/CROCODILE-CESM/CrocoDash/discussions/84>


You can also check out the Regional MOM6 documentation for more support information `here <https://regional-mom6.readthedocs.io/en/latest/>`_!