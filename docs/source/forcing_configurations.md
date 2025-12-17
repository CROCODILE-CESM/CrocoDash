# Forcing Configuration

Forcing Configuration is handled by the forcing_configurations.py module. How it works:

1. Each forcing configuration option in the module, like tides, chlorophyll, or runoff mapping states the arguments it needs and the compset requirements. 

2. The ForcingConfigRegistry registed all of these options. I can provide what configuration option is required or valid based on the compset and/or input arguments

3. In the Case workflow, this is all handled in configure_forcings. It initialize the FOrcingConfigRegistry





