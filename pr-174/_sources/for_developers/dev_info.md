# Get started developing!

## Installation

[Follow the installation docs!](../installation.md)

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


## Recognition and Appreciation

All contributors are valued! We appreciate:
- Code contributions
- Bug reports and testing
- Documentation and tutorials
- Help with issues and discussions
- Feature ideas and feedback

Thank you for making CrocoDash better!
