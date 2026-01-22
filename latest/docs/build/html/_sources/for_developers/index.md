# Developer Information

Welcome to the CrocoDash developer documentation! This section contains everything you need to understand, develop, and contribute to CrocoDash.

## Getting Started

If you're new to CrocoDash development, start here:

1. [Development Environment Setup](dev_environment.md) - Set up your local development environment
2. [Project Architecture](project_architecture.md) - Understand how CrocoDash is organized
3. [Common Development Tasks](common_dev_tasks.md) - Learn how to accomplish typical development work

## Development Guides

```{toctree}
:maxdepth: 1

dev_environment
project_architecture
common_dev_tasks
contributing
docs
adding_data_access
```

## Detailed Topics

### Implementation and Extension

- [Adding Data Sources](adding_data_access.md) - How to add new data products to the data access module
- [Writing Documentation](docs.md) - How to write and build documentation

### Code Standards and Practices

See [Contributing Guidelines](contributing.md) for:
- Code style and standards
- Type hints and docstrings
- Test requirements
- Pull request process
- Code review expectations

## Key Concepts

### Validation
Configure Forcings is where all validation of options should be done. For example:
- Chlorophyll cannot be provided if BGC is not in the compset
- River nutrients cannot be implemented if runoff or BGC is not in the compset

See `ForcingConfigRegistry.configure_forcings()` for implementation patterns.

### Modular Forcing Extraction
The `extract_forcings` module is designed to divorce OBC & IC generation from the main Case workflow because the process is complex and computationally intensive.

## Common Workflows

### Adding a New Feature
1. Create a feature branch: `git checkout -b feature/my-feature`
2. Set up development environment (if not done): [Dev Environment Setup](dev_environment.md)
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
- See [Contributing Guidelines](contributing.md#getting-help) for more support options
