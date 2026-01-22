# Get started developing!

## Prerequisites

- Git and basic command-line familiarity
- Conda or Mamba package manager
- A CESM installation (if testing full case workflow)
- Access to the required data repositories (GDEX, CESM inputdata, etc.)

## Initial Setup

Follow the installation docs!

## Development Workflow

### Making Code Changes

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/my-feature-name
   ```

2. **Make your changes** to the relevant files in the `CrocoDash/` directory

3. **Run tests locally** to ensure nothing broke:
   ```bash
   pytest tests/
   ```

   Or run specific test files:
   ```bash
   pytest tests/test_specific.py
   ```

### Testing During Development

CrocoDash uses `pytest` for testing. Key testing practices:

- **Run full test suite:** `pytest tests/`
- **Run with verbose output:** `pytest -v tests/`
- **Run specific test:** `pytest tests/test_file.py::test_function_name`
- **Run and stop on first failure:** `pytest -x tests/`
- **Show print statements:** `pytest -s tests/`

Always run tests after making changes to ensure you haven't introduced regressions.

### Working with Extract Forcings

The `extract_forcings` module is computationally intensive and may involve large data transfers. When developing this module:

1. Use small test cases with limited date ranges
2. Test with small spatial domains
3. Consider using the `preview: true` option in configuration files to test without full computation
4. Use the `--test-config` flag if available to validate configuration before running

### Working with Raw Data Access

When adding or modifying data access functions:

1. Ensure your function follows the `ForcingProduct` base class interface
2. Test with real data if possible, or mock data if that's not feasible
3. Add proper error handling for network/file access failures
4. Update the registries in `raw_data_access/registry.py`


## Debugging


## Common Issues and Solutions

### Issue: Submodules show as empty

**Solution:** Run `git submodule update --init --recursive`

### Issue: Import errors for CrocoDash modules

**Solution:** Ensure you're in the correct directory and the conda environment is activated. You can also install in development mode:

```bash
pip install -e .
```

This allows imports from anywhere after installation.

### Issue: Tests fail due to missing data

**Solution:** Some tests may require specific datasets. Check if there's a glade requirement

## Keeping Your Fork/Branch Updated

If working on a fork or long-running branch:

```bash
# Fetch latest changes from upstream
git fetch upstream

# Rebase your branch on the latest main
git rebase upstream/main

# Force push to your branch (only if you're the sole contributor)
git push -f origin feature/my-feature-name
```



## Next Steps

After setting up your development environment, read the [Project Architecture](project_architecture.md) guide to understand the codebase


## Recognition and Appreciation

All contributors are valued! We appreciate:
- Code contributions
- Bug reports and testing
- Documentation and tutorials
- Help with issues and discussions
- Feature ideas and feedback

Thank you for making CrocoDash better!
