CrocoDash Structure
=====================

CrocoDash is designed to be one tool that manages the workflow from input data sources into a regional MOM6 in CESM run. It can be structured into three sections

Grid Generation
----------------
CrocoDash wraps the mom6_bathy module for supergrid, vertical grid, and topo generation. One function that doesn't come from mom6_bathy is interpolate_from_file, which is a wrapper around RM6 setup_bathymetry

Case Creation
---------------
CrocoDash wraps the VCG module for case creation with some light argument passing.

Boundary Condition & Initial Condition Creation
------------------------------------------------
CrocoDash wraps RM6 to provide Boundary Conditions