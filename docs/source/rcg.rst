Regional Case Gen
==================

This module takes the output from RM6 and configures it for a CESM run of MOM6. It contains two functions, a Write_ESMF, and setup_cesm function. 

write_ESMF
----------
Copied from VCG, needed for the CESM run.

setup_cesm
----------

This function wraps write_esmf and sets up the CESM run. 

Features:

#. Rearrange the RM6 input folder to the correct format of CESM (i.e. take everything out of the forcing folder)
#. Moves MOM_input to correct place in CESM run (SourceMods/src.mom/)
#. Add specific variables to the MOM_override we need (OCEAN_NX, ...)
#. Call write_esmf
#. XML changes to point to the input folder


