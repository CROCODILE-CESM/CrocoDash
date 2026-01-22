# Setting Up Your Development Environment

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

## Documentation Development

### Building Documentation Locally

1. **Navigate to the docs folder:**
   ```bash
   cd docs
   ```

2. **Build HTML documentation:**
   ```bash
   make html
   ```

   This generates HTML in `docs/build/html/`. Open `index.html` in your browser to view.

3. **Clean and rebuild** (if docs seem stale):
   ```bash
   make clean
   make html
   ```

### Regenerating API Documentation

When you add new modules or submodules to CrocoDash, regenerate the API documentation:

```bash
cd docs
sphinx-apidoc -o source/api-docs ../CrocoDash
make html
```

This scans the CrocoDash package and auto-generates documentation from docstrings.

### Preview Documentation on a Supercomputer

If you're on a supercomputer with restricted internet, you can still preview locally:

```bash
cd docs
make serve
```

This starts a local server. Access it through your browser (the command will print the URL).

### Documentation Troubleshooting

- **"make: command not found"** - Ensure you've activated the conda environment with `sphinx` installed
- **Docs not updating** - Run `make clean` before `make html` to remove cached files
- **API docs missing new modules** - Did you run `sphinx-apidoc`? Did you import the modules in `__init__.py`?
- **Sphinx errors about undefined references** - Check that file paths and function names are correct in your markdown

## Remote Development on Supercomputers

CrocoDash is primarily developed on HPC systems like NCAR's Derecho or GLADE. Some specific considerations:

### Module Loading

Some systems require loading modules before Python/conda works properly:

```bash
module load conda  # if required on your system
```

Check your supercomputer's documentation for required modules.

### Batch Job Development

For computationally expensive development (like testing `extract_forcings`), you may need to submit batch jobs:

```bash
# Create a simple script to test your changes
cat > test_job.sh << 'EOF'
#!/bin/bash
#PBS -l select=1:ncpus=10:mem=50GB
#PBS -l walltime=01:00:00
#PBS -q queue_name

module load conda
mamba activate CrocoDash
cd /path/to/CrocoDash

pytest tests/test_extract_forcings.py
EOF

qsub test_job.sh
```

### Data Access on Supercomputers

- Understand your system's data storage hierarchy (home, scratch, campaign directories)
- Use scratch space for temporary data; clean up when done
- Be aware of file retention policies (scratch is often cleaned periodically)
- Use direct paths instead of symlinks when possible for better performance

## Debugging

### Using Print Statements

For quick debugging, add print statements and run tests with `-s`:

```bash
pytest -s tests/test_file.py::test_function_name
```

### Using a Debugger

For more complex debugging, use `pdb`:

```python
import pdb

def my_function():
    pdb.set_trace()  # Execution pauses here
    # Debug commands: n (next), s (step), c (continue), p variable_name
```

Or use an IDE with built-in debugging (e.g., VS Code, PyCharm).

### Debugging Jupyter Notebooks

If working with notebooks in the `dev/` folder:

```bash
jupyter notebook dev/my_notebook.ipynb
```

Then use notebook cells to test code incrementally.

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

**Solution:** Some tests may require specific datasets. Check if there's a test configuration or fixtures directory. You may need to download test data or mock it.

### Issue: Documentation won't build

**Solution:** Try the troubleshooting steps above. If persistent, check that all required Sphinx extensions are installed:

```bash
mamba install sphinx myst-parser sphinx-rtd-theme
```

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

After setting up your development environment:

1. Read the [Project Architecture](project_architecture.md) guide to understand the codebase
2. Check out [Common Development Tasks](common_dev_tasks.md) for specific workflows
3. Review [Contributing Guidelines](contributing.md) before submitting changes
