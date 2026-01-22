# Forcing Configuration

Forcing Configuration is handled by the `forcing_configurations.py` module.

## How it works

1. Each forcing configuration option in the module, like tides, chlorophyll, or runoff, specifies the arguments it needs and its compset requirements.

2. The `ForcingConfigRegistry` registers all of these options. It can provide which configuration options are required or valid based on the compset and/or input arguments.

3. In the `Case` workflow, this is all handled in `configure_forcings`. It initializes the `ForcingConfigRegistry` with all the keyword arguments provided by the user. Based on those options, it finds the configuration options and configures the corresponding forcings. (It will fail if the required configuration options are not provided.)

## Some Helper Functions

Here are some useful helper functions to understand what you need for each configuration option and which configuration options you must provide.

```python
from CrocoDash.forcing_configurations import *

# Find required options
required_options = ForcingConfigRegistry.find_required_configurators(compset)

# Find possible options
valid_options = ForcingConfigRegistry.find_valid_configurators(compset)

# Find user-required arguments for a configurator class
user_args = ForcingConfigRegistry.get_user_args(configurator_class)

# Example usage:
req_opts = ForcingConfigRegistry.find_required_configurators(compset)
user_args_for_first = ForcingConfigRegistry.get_user_args(req_opts[0])
```

## In the Case workflow

The Case.configure_forcings method runs all the helper functions you need and will fail if any required configuration options or arguments are missing.