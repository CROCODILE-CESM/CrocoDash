Tides
================

MOM6 can take tides data as a boundary condition in the regional domain. Many tides parameters are impacted by this and can be seen in case.process_forcings.

In our workflow, we take data from the TPXO tidal model and regrid onto our grid.

TPXO model data can be requested off of the TPXO website or is available on derecho.

The file paths of the tidal files can be passed into configure forcings as shown in the CrocoGallery "Add Tides" demo with all wanted tidal constituents, like M2.