# Developer Guide

Welcome! If you want to understand, modify, or extend CrocoDash, start here.

## Start with the architecture

The **[Architecture](architecture.md)** page covers how the modules fit
together, which registries CrocoDash exposes, where to add new things, and how
to run the tests. Read that first if you're new to the codebase.

## Extension guides

CrocoDash is designed to be extended without touching core code. Two common
extension points have dedicated guides:

- **[Adding a forcing configuration](adding_forcing_configurations.md)** — a
  new configurator for tides, BGC, rivers, salt restoring, etc.
- **[Adding a data source](adding_data_access.md)** — a new raw dataset in
  `raw_data_access/`.

## Reference

- **[Submodule API usage](submodule_api_usage.md)** — every function CrocoDash
  calls from `regional-mom6`, `mom6_forge`, and `visualCaseGen`. Keep this
  handy when upstreams change.
- **[Writing documentation](edit_docs.md)** — how to build and contribute to
  these docs.

```{toctree}
:maxdepth: 1

architecture
adding_data_access
adding_forcing_configurations
submodule_api_usage
edit_docs
Semi-Official ChangeLog <https://github.com/CROCODILE-CESM/CrocoDash/discussions/138>
```

## Project links

- [GitHub Repository](https://github.com/CROCODILE-CESM/CrocoDash)
- [Issues](https://github.com/CROCODILE-CESM/CrocoDash/issues)
- [Pull Requests](https://github.com/CROCODILE-CESM/CrocoDash/pulls)
- [CROCODILE Project](https://github.com/CROCODILE-CESM)

## Questions?

- Search existing [GitHub Discussions](https://github.com/CROCODILE-CESM/CrocoDash/discussions)
- Open a new discussion for questions
