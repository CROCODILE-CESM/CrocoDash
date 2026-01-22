# Contributing to CUPiD

CUPiD is a tool for the CESM community, driven by community. If you have an idea for diagnostics, use cases, or new features, your contribution will be incredibly valuable!

The CUPiD docs have resources for developing new diagnostics. Please consult these if you would like to create new notebooks or examples:
- [CUPiD Contributors Guide](https://ncar.github.io/CUPiD/contributors_guide.html)
- [How to Add New Notebooks to CUPiD](https://ncar.github.io/CUPiD/addingnotebookstocollection.html)

There are a few techinical steps in the contributor's guide (see link above) that we will not discuss here; let us know if you run into any issues with `pre-commit` or GitHub.
New diagnostics notebooks can become part of an existing diagnostics workflow (see [CUPiD/examples](https://github.com/NCAR/CUPiD/tree/main/examples)) or you can create your own example with a new config file.

## Overview
The structure of CUPiD can be confusing, but contributing is easy! Here are the basic steps of adding notebooks:
1. Have an idea for diagnostics or analysis of a component of CESM output
2. Design a Jupyter notebook that operates on CESM history (one time step, multiple variables) or timeseries (one variable, multiple time steps) files
3. Add a cell for parameters that CUPiD will inject (see [how to add new notebooks](https://ncar.github.io/CUPiD/addingnotebookstocollection.html)). These are flexible, but variables can be tricky to add within the CUPiD workflow so be mindful.
4. Create/modify a `config.yml` file to populate and run your new notebook(s)!

## Making a (Sub)-Project for the 2025 CrocoDash Workshop
If you want to work with CUPiD and diagnostics as part of your 2025 Workshop project, let us know! You'll be making so many cool regional models, and you might need new cool metrics and visualizations to look at them! Here are a couple resources that might help get you started on ideas:
- [MOM6-Tools](https://mom6-tools.readthedocs.io/examples.html) - this python package is designed and maintained by Gustavo Marques at NCAR (extra points if you talk to him this week)! It primarily hosts tools for global ocean models; maybe they could also work for regional models?
- [MOM6 Analysis Cookbook](https://mom6-analysiscookbook.readthedocs.io/en/latest/) - from COSIMA, our collaborators in Australia! This notebook provides some more specialized tools/techniques for working with MOM6 data like xgcm and **budgets**.
- [EKE Calculation](../projects/CARIB12_EKE_TS.ipynb) - from Giovanni Seijo-Ellis (look for him at the workshop!). This notebook calculates Eddy Kinetic Energy, specifically for a region in the Caribbean. How could we generalize this? What other metrics could we calculate?

## CUPiD Structure
- `nblibrary`: where new notebooks will go. They are categorized by component (e.g. ocean - ocn and atmosphere - atm). Notebooks are run here by CUPiD then copied to the path from `run_dir` in the config file.
- `examples`: config files for different workflows. The config files determine which notebooks are run and what parameters are passed in.
- `helper_scripts`: infrastructure that translates CESM variables/settings to CUPiD config information and parameters. You will need to edit this if your workflow/notebook is designed to run immediately after a CESM run.

## Advice for Contributors
For CrocoDash, we created a new example, `regional_ocean_report_card`, with a new set of notebooks for regional ocean diagnostics; based on this experience these are some guidelines and notes for development.

### Miscellanous Notes:
- Try to run all notebooks with the `cupid-analysis` conda env. The conda environment can be changed in the config file, but a universal environment is powerful.
- If there are functions common across multiple notebooks, consider adding a `utils.py` in the same directory as the notebook, this can house light and reusable functions.
  - Beware! CUPiD works by executing the specified notebooks in the `nblibrary` folder and then copying them to the output directory. Additional files and folders (like `utils.py`) are not copied over (this might change in future versions). This means users would need to manually copy over any dependencies if they want to rerun the notebook.
- When saving images or other output, consider adding a an output path parameter in the notebook or you can cheat and save them in the timeseries or CESM output directory.
- Think about how flexible your notebook is between different timescales, regions, and data outputs.
- If something is missing in the CUPiD workflow, make an issue or a pull request!

### Adding Notebook Specific Parameters
You can add as many notebook specific parameters as you want, but they can be difficult to populate automatically in the CESM workflow.

When you add custom variables that will depend on the specific CESM case (e.g. location of data or region specific information),
you will also need to update `cesm_postprocessing.sh` and `generate_cupid_config_for_cesm_case.py` scripts in `CUPiD/helper_scripts`.
These handle the translation of information from the CESM case to CUPiD config settings.

> **Example:**
>
> For the open boundary conditions notebook `Regional_Ocean_OBC.ipynb`, the boundary conditions are only accessible through the MOM6 input directory.
> The input directory is not available through the CESM output directory, but the path to the input directory is accessible through the CESM case directory.
>
> We added the path to the case directory as a parameter in the notebook. Then we needed to add the following to `generate_cupid_config_for_cesm_case.py`:
>
> ```
> if "Regional_Ocean_OBC" in my_dict["compute_notebooks"].get("ocn", {}):
>       my_dict["compute_notebooks"]["ocn"]["Regional_Ocean_OBC"]["parameter_groups"]["none"]["case_root"] = case_root
> ```
>