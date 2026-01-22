# Understanding CrocoDash's Structure

CrocoDash is designed to be one tool that manages the workflow from input data sources into a regional MOM6 in CESM run. It can be structured into three sections:

1. Grid Generation
2. CESM Interface / Case Creation
3. Forcing File Generation

## Grid Generation

CrocoDash wraps the mom6_bathy module for supergrid, vertical grid, and topo generation. One function that doesn't come from mom6_bathy is interpolate_from_file, which is a wrapper around RM6 setup_bathymetry

## Case Creation

CrocoDash wraps the VisualCaseGen module for case creation with some light argument passing.

## Forcing File Generation

CrocoDash wraps RM6 to provide Initial & Boundary Conditions

