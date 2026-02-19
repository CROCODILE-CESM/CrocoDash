# Shareable Configuration

Ever wanted to share your regional MOM6 setup? Get a summary of your unique changes? Let someone else easily run your model? This module is for you!

Importable through `CrocoDash.shareable`, we've got a whole host of tools to do the following:

1. **Inspect** - Identify the unique information in your CESM case
   - CrocoDash initialization arguments (grids, topography, vertical grid)
   - Forcing configurations (tides,chlorophyll, etc..)
   - Unique XML file
   - SourceMods files
   - Parameter changes in `user_nl_*` files
   - Returns this information in a manifest dictionary

2. **Bundle** - Package your unique case information into a folder & portable zip file
   - Automatically collects all modified files and configurations from the inspect manifest
   - Includes forcing data files and ocean/ice inputs

3. **Fork** - Create a new case from a bundled configuration
   - Recreate your setup with user inputted different compsets or configurations
   - Reuse the same grid, topography, and vertical structure

4. **Apply** - Transfer unique settings from one case to another
   - Propagate parts of your bundle to new experiments
   - (Mostly is a helper module for Fork) (But savvy users can use these functions to!)

## Usage

```python
from CrocoDash.shareable.inspect import identify_non_standard_case_information
from CrocoDash.shareable.bundle import bundle_case_information
from CrocoDash.shareable.fork import fork


# Identify what makes your case unique
case_info = identify_non_standard_case_information(caseroot, cesmroot, machine, project)

# Bundle it into a shareable format
bundle_path = bundle_case_information(case_info, output_folder)

# Fork your case to a new case
fork(bundle_path, cesmroot, machine, project_number, caseroot, inputdir)

```

Check out the CrocoGallery shareable demo if ya like!