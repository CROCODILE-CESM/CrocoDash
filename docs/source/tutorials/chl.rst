Chlorophyll
================

MOM6 can take chlorophyll data as a file in the regional domain. It impacts shortwave penetration. MOM6 parameters that are impacted by it CHL_FROM_FILE, CHL_FILE, VAR_PEN_SW, and PEN_SW_NBANDS.
In our workflow, we take raw data from SeaWIFS, process it globally, and subset to our regional domain. 

.. caution:: 

    This method does not do a great job of resolving chlorophyll in estuaries and similar features, if possible, the generated chlorophyll file should be replaced with a
    better product (which can be done by replacing the file in CHL_FILE)

The global processed chlorophyll file is hosted on the CESM inputdata svn server under ocn/mom/croc/chl/data and can be accessed through the CrocoDash raw_data_access module like below:

.. code-block:: python

    from CrocoDash.raw_data_access.datasets import seawifs as sw
    sw.get_processed_global_seawifs_script_for_cli(
        output_dir="<insert_dir>",
        output_file="get_seawifs_data.sh"
    )

The file path of the global file (after running the script from the code block) can be passed into configure forcings as shown in the CrocoGallery "Add CHL" demo.