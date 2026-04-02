# Want to do more?

Welcome to the CrocoDash developer documentation! This section contains everything you need to understand, develop, and contribute to CrocoDash.

## Getting Started

If you're new to CrocoDash development, start here:

1. [Development Information](dev_info.md) - Read how to get started
2. [Project Architecture](../for_users/structure.md) - Understand how CrocoDash is organized

## Development Guides

```{toctree}
:maxdepth: 1

dev_info
edit_docs
adding_data_access
adding_forcing_configurations
```

## Detailed Topics

### Implementation and Extension

- [Adding Data Sources](adding_data_access.md) - How to add new data products to the data access module
- [Adding Forcing Configurations](adding_forcing_configurations.md) - How to add new forcing configurations to configure_forcings
- [Writing Documentation](edit_docs.md) - How to write and build documentation

## Key Concepts

### Validation
Configure Forcings is where all validation of forcings should be done. For example:
- Chlorophyll cannot be provided if BGC is not in the compset
- River nutrients cannot be implemented if runoff or BGC is not in the compset

See `case.configure_forcings()` for implementation patterns.

### Modular Forcing Extraction
The `extract_forcings` module is designed to divorce computationally heavy processes from the main Case workflow because the process is complex and computationally intensive.

## Common Workflows

### Adding a New Feature
1. Create a feature branch: `git checkout -b feature/my-feature`
2. Set up development environment 
3. Make your code changes with proper docstrings and type hints
4. Write tests for your changes
5. Build and test documentation: `cd docs && make html`
6. Submit a pull request with description
7. Respond to code review feedback

### Adding a New Data Source
1. Follow the guide in [Adding Data Sources](adding_data_access.md)
2. Create a class inheriting from `ForcingProduct`
3. Update registries in `raw_data_access/registry.py`
4. Write comprehensive tests
5. Update data access documentation if relevant

### Fixing a Bug
1. Open or find the relevant issue
2. Create a fix branch: `git checkout -b fix/issue-description`
3. Write a test that reproduces the bug
4. Fix the bug (now your test should pass)
5. Submit a pull request referencing the issue

## Project Links

- [GitHub Repository](https://github.com/CROCODILE-CESM/CrocoDash)
- [Issues](https://github.com/CROCODILE-CESM/CrocoDash/issues)
- [Pull Requests](https://github.com/CROCODILE-CESM/CrocoDash/pulls)
- [CROCODILE Project](https://github.com/CROCODILE-CESM)

## Questions?

- Check existing [GitHub Discussions](https://github.com/CROCODILE-CESM/CrocoDash/discussions)
- Open a new discussion for questions
