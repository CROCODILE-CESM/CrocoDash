Understanding CrocoDash's Structure
======================================

CrocoDash is designed to be one tool that manages the workflow from input data sources into a regional MOM6 in CESM run. It can be structured into three sections: 

1. Grid Generation 
2. CESM Interface / Case Creation
3. Forcing File Generation

Grid Generation
----------------
CrocoDash wraps the mom6_bathy module for supergrid, vertical grid, and topo generation. One function that doesn't come from mom6_bathy is interpolate_from_file, which is a wrapper around RM6 setup_bathymetry

Case Creation
---------------
CrocoDash wraps the VisualCaseGen module for case creation with some light argument passing.

Forcing File Generation
------------------------------------------------
CrocoDash wraps RM6 to provide Initial & Boundary Conditions

Workflow Diagram
------------------
The following diagram illustrates the workflow of CrocoDash to set up a regional model:

.. figure:: _static/workflow_diagram.png
   :alt: Workflow diagram showing the steps from CrocoDash to a regional model.
   :align: center
   :width: 80%

   **Workflow Diagram**: This diagram shows the key steps involved in using CrocoDash to form a fully configured regional model.

Module Diagram
----------------
The following diagram describes the connections between various modules and the `case.py` file:

.. figure:: _static/module_diagram.svg
   :alt: Module diagram showing connections to case.py.
   :align: center
   :width: 80%

   **Module Diagram**: This diagram highlights how different modules interact with the main workflow (`case.py`) file in CrocoDash.