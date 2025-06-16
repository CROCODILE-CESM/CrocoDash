Large Data Workflow
====================

Generating open boundary condition (OBC) data is essential for the entire model runtime but can be time-consuming and resource-intensive. 
The Large Data Workflow in CrocoDash helps manage this by breaking data access into smaller, more manageable components.

Workflow Overview
------------------

The workflow is enabled by setting the `too_much_data` boolean in `case.configure_forcings`. This triggers the copying of a script folder into the case input directory forcing folder 
and the generation of a configuration file to download the required boundary condition files. An example of this is in CrocoGallery under features/add_data_products.ipynb.
Users can trigger the workflow by running driver.py in the forcing folder and adjusting config options in the config file.

Folder Structure
------------------

- **config.json** – Defines the region-specific requirements and run parameters.
- **README** – Explains the workflow.
- **driver.py** – Executes all scripts needed to obtain OBC data.
- **Code/** – Contains all scripts used in the workflow.
- **raw_data/**, **regridded_data/** – Intermediate storage for workflow steps, preventing the need to rerun all scripts at once.

Scripts
-------------

1. **get_data_piecewise** – Retrieves raw, unprocessed data in chunks (size defined by `config["params"]["step"]`) and saves it to `config["raw_data"]`.
2. **regrid_data_piecewise** – Processes raw data and stores it in `config["regridded_data"]`.
3. **merge_piecewise_dataset** – Combines regridded data into the final dataset for model input.

How to Use
-------------

1. Identify and allocate available computing resources.
2. Adjust the `step` parameter to match resource constraints (default: 5 days).
3. Run each step manually or use `driver.py` as a guide.

Check out the demo `here <https://crocodile-cesm.github.io/CrocoGallery/notebooks/features/too_much_data.html>`_.
