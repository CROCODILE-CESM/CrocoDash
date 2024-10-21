Grid Gen Module
==================

This module generates the Hgrid, Vgrid, and Bathymetry in two different ways:

For Hgrid and Bathy:

#. Using the RM6 straight generation of the H + V grid + GEBCO for Bathymetry
#. Subsetting Global Hgrid and Topo from Fred/Frank's work 

For Vgrid:

#. Using the RM6 straight generation of the Vgrid
#. Accepting a user defined Vgrid which either must have a midpoint called `zl` or a thickness (default `dz`) of which we can define the midpoints & interfaces.

Other Features:

#. Mask out unwanted ocean by selecting a point inside the ocean we want. For example, the NWA12 grid includes a tiny bit of the Pacific Ocean and Hudson Bay. We don't want those and can mask them out by picking a point in the Atlantic.