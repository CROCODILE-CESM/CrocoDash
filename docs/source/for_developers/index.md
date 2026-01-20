# Developer Information

Random Notes:

1. Configure Forcings is where all validation of options should be done (e.g. Chlorophyll cannot be provided if BGC is in the compset, or river nutrients cannot be implemented if runoff or bgc is not in compset)
2. extract_forcings is a module to divorce the OBC & IC generation from the Case workflow (because it's complicated and large)

```{toctree}
:maxdepth: 1

docs
adding_data_access
```
