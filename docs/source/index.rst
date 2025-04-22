.. CrocoDash documentation master file, created by
   sphinx-quickstart on Fri Oct 18 11:22:10 2024.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

CrocoDash Documentation
=======================================

Welcome to the CrocoDash Documentation! Get quick-started by heading over to :ref:`installation`! 

Background
-------------
CrocoDash is part of the `CROCODILE project <https://github.com/CROCODILE-CESM>`_, and spun off of the `regional-mom6 (RM6) package <https://github.com/CROCODILE-CESM/regional-mom6>`_, an independent package that sets up a regional MOM run. CrocoDash wraps RM6 (for OBC construction & some grid generation) to setup a workflow inside the CESM.

Motivation
-------------
Please see the overall CROCODILE project for scientific motivation. CrocoDash provides a platform to combine MOM6 and CESM tools to create a sum greater than the parts for regional cases.

Description
----------------
CrocoDash brings regional MOM6 inside the CESM. It is a lightweight package that ties together each part of the MOM6 in CESM setup process into one package.
1. Grid Generation (Through `mom6_bathy <https://github.com/NCAR/mom6_bathy>`_ and `regional-mom6 <https://github.com/CROCODILE-CESM/regional-mom6>`_)
2. CESM Setup (Through `VisualCaseGen <https://github.com/CROCODILE-CESM/VisualCaseGen>`_)
3. Forcing + OBC Setup (Through CESM & `regional-mom6 <https://github.com/CROCODILE-CESM/regional-mom6>`_)

CrocoDash also provides a variety of helper tools to help setup a case, for example, a tool to edit bathymetry (TopoEditor) or a tool to download public datasets simply (data_access module). 


Demos
--------
There are a few demos to get used to the CrocoDash. Check out the demos folder:

1. One is called `minimal_demo_rect <demos/minimal_demo_rect.ipynb>`_. It creates a rectangular case from grid generation to CESM case submission. 

2. Another demo is called `minimal_demo_subset_global <demos/minimal_demo_subset_global.ipynb>`_, which is similar to the previous demo but subsets a global grid instead of generating a rectangular grid. 

3. Another demo showcases the ability to have less than four boundaries in a regional domain. The demo is `minimal_demo_three_boundary <demos/minimal_demo_three_boundary.ipynb>`_.



.. toctree::
   :maxdepth: 2
   :caption: Contents:

   installation
   demos
   features/index
   developers/index
   api-docs/modules


You can also check out the Regional MOM6 documentation for more support information about those functions `here <https://regional-mom6.readthedocs.io/en/latest/>`_!