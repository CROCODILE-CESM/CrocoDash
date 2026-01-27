# Forcing Configuration

Forcing configuration handles setup of all forcing and boundary conditions for your regional MOM6 case, including tides, biogeochemistry, runoff, initial conditions, and more.

## Overview

Forcing configuration is managed by the `forcing_configurations.py` module through a registry-based system:

1. **Each configuration option** (Tides, BGC, Rivers, etc.) is a separate class that inherits from `BaseConfigurator`
2. **The `ForcingConfigRegistry`** automatically registers all these options and determines which are required or valid based on your compset
3. **The `Case.configure_forcings()` method** orchestrates the configuration process:
   - Takes your configuration inputs (files, options, parameters)
   - Validates required configurations are provided
   - Instantiates active configurators
   - Applies CESM/MOM6 case settings
   - Serializes configuration for forcing extraction

## Common Configuration Examples

Here are typical forcing configurations you might use:

### Tidal Forcing
```python
case.configure_forcings(
    tpxo_elevation_filepath="/path/to/h_tpxo9.v1.nc",
    tpxo_velocity_filepath="/path/to/u_tpxo9.v1.nc",
    tidal_constituents=["M2", "K1"],
    start_date="2000,01,01"
)
```

### Biogeochemistry (BGC)
```python
case.configure_forcings(
    # BGC configuration if "MARBL" in compset
    marbl_ic_filepath="/path/to/bgc_ic.nc",
    # ... other BGC options
)
```

### Runoff
```python
case.configure_forcings(
    # Runoff configuration if "DROF" in compset
    runoff_esmf_mesh_filepath="/path/to/glofas_mesh.nc",
    rmax=8,
    # ... other runoff options
)
```

## How to Check What's Required

Before calling `configure_forcings()`, you can check what configuration options are required for your compset. It will also be printed on case initialization:

```python
from CrocoDash.forcing_configurations import ForcingConfigRegistry

compset = "1850_DATM%NYF_SLND_SICE_MOM6%MARBL-BIO%REGIONAL_DROF%GLOFAS_SGLC_SWAV"

# Find required configurations
required = ForcingConfigRegistry.find_required_configurators(compset)
for config_class in required:
    print(f"Required: {config_class.name}")
    user_args = ForcingConfigRegistry.get_user_args(config_class)
    print(f"  Requires these inputs: {user_args}")

# Find optional configurations
valid = ForcingConfigRegistry.find_valid_configurators(compset)
for config_class in valid:
    if config_class not in required:
        print(f"Optional: {config_class.name}")
```

## Helper Functions

Useful functions for understanding configuration requirements:

```python
from CrocoDash.forcing_configurations import ForcingConfigRegistry

# Find required configurators for your compset
required = ForcingConfigRegistry.find_required_configurators(compset)

# Find all valid/compatible configurators
valid = ForcingConfigRegistry.find_valid_configurators(compset)

# Get user-required arguments for a specific configurator
user_args = ForcingConfigRegistry.get_user_args(configurator_class)

# Find what inputs are missing
missing = ForcingConfigRegistry.return_missing_inputs(configurator_class, inputs_dict)

# Check if a configurator is compatible with your compset
is_compatible = configurator_class.validate_compset_compatibility(compset)
```

## In the Case Workflow

When you call `case.configure_forcings(**kwargs)`, CrocoDash automatically:

1. **Validates** that all required configurations are provided
2. **Checks** that you've provided all required inputs
3. **Instantiates** the appropriate configurators
4. **Applies** settings to your CESM case
5. **Serializes** configuration for use by `extract_forcings`

If something is missing, you'll get an error message telling you exactly what's needed.

## Configuration JSON Files

Your configuration will be saved to JSON for reproducibility in the `extract_forcings/config.json` file in your input directory:

The JSON structure organizes inputs and outputs by configurator name, allowing `extract_forcings` to generate forcing and boundary condition files.

## Understanding Your Compset

Which configurations are required depends on your compset string. Common components:

- **`MOM6`** - Ocean component (almost always required for regional cases)
- **`MARBL-BIO`** - Biogeochemistry (requires BGC configuration)
- **`CICE`** - Sea ice (may require ice configuration)
- **`DROF%GLOFAS`** - Runoff from GLOFAS data (requires runoff mapping)

Your specific compset determines which forcing configurations are triggered.

## Troubleshooting Configuration Issues

**"Missing required inputs" error:**
- Check what your compset requires using `find_required_configurators()`
- Ensure you've provided all user-required arguments
- Verify file paths exist and are accessible

**Configuration not being applied:**
- Check if it's actually valid for your compset with `validate_compset_compatibility()`
- Verify you haven't misspelled configuration parameter names, because they must be exact to be triggered

**"Configuration not active" message:**
- This is informational - the configuration isn't required, compatible, or requested with your compset
- Only provide inputs for configurations you actually need

## Want to add more?

To add a new forcing configuration, See [Adding Forcing Configurations](../for_developers/adding_forcing_configurations.md) in the developer documentation

## See Also

- [Available Datasets](datasets.md) - What data sources can be used
- [Available Compsets](available_compset_alias.md) - Valid compset options
- [Tutorials](https://crocodile-cesm.github.io/CrocoGallery/) - Working examples with real cases