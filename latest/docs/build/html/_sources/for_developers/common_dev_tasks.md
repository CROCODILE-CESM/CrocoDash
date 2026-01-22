# Common Development Tasks

This guide covers common tasks you'll encounter while developing CrocoDash.

## Adding a New Module

### Step 1: Create the Module File

Create a new Python file in the appropriate location within `CrocoDash/`:

```bash
touch CrocoDash/my_new_module.py
```

Or for a submodule:

```bash
mkdir -p CrocoDash/my_submodule/
touch CrocoDash/my_submodule/__init__.py
touch CrocoDash/my_submodule/core.py
```

### Step 2: Write Code with Docstrings

Follow PEP 257 docstring conventions:

```python
"""
Module description.

This module does something important.
"""

def my_function(param1: str, param2: int) -> bool:
    """
    Brief description.
    
    Longer description explaining what this function does, including
    any important details or caveats.
    
    Parameters
    ----------
    param1 : str
        Description of param1
    param2 : int
        Description of param2
        
    Returns
    -------
    bool
        Description of return value
        
    Examples
    --------
    >>> my_function("test", 42)
    True
    """
    return True

class MyClass:
    """Brief class description.
    
    Longer description of the class.
    """
    
    def __init__(self, value: int):
        """
        Initialize MyClass.
        
        Parameters
        ----------
        value : int
            Initial value
        """
        self.value = value
```

### Step 3: Update API Documentation

Regenerate the API docs to include your new module:

```bash
cd docs
sphinx-apidoc -o source/api-docs ../CrocoDash
make html
```

Verify that your module appears in `source/api-docs/` and that its documentation looks correct in the built HTML.

### Step 4: Add to Package Imports (if needed)

If your module should be accessible from the top level, add it to `CrocoDash/__init__.py`:

```python
from CrocoDash.my_new_module import MyClass, my_function

__all__ = ["MyClass", "my_function"]
```

### Step 5: Write Tests

Create a test file:

```bash
touch tests/test_my_new_module.py
```

See the "Writing Tests" section below for details.

## Writing Tests

Tests should cover normal cases, edge cases, and error conditions.

### Test Structure

```python
# tests/test_my_module.py

import pytest
from pathlib import Path
from CrocoDash.my_module import MyFunction, MyClass

# Fixtures for common setup
@pytest.fixture
def sample_data():
    """Provide sample data for tests."""
    return {"key": "value"}

@pytest.fixture
def temp_file(tmp_path):
    """Create a temporary file for testing."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("test content")
    return file_path

# Normal case tests
class TestMyFunction:
    """Tests for my_function."""
    
    def test_basic_functionality(self, sample_data):
        """Test normal operation."""
        result = MyFunction(sample_data)
        assert result is not None
        assert result["key"] == "value"
    
    def test_with_different_inputs(self):
        """Test with various inputs."""
        assert MyFunction({}) == {}
        assert MyFunction({"a": 1}) == {"a": 1}

# Edge case tests
class TestMyFunctionEdgeCases:
    """Edge case tests."""
    
    def test_empty_input(self):
        """Test with empty input."""
        assert MyFunction({}) == {}
    
    def test_large_input(self):
        """Test with large input."""
        large_dict = {f"key_{i}": i for i in range(10000)}
        result = MyFunction(large_dict)
        assert len(result) == 10000

# Error handling tests
class TestMyFunctionErrors:
    """Tests for error handling."""
    
    def test_invalid_input_type(self):
        """Test error on invalid input type."""
        with pytest.raises(TypeError):
            MyFunction("not a dict")
    
    def test_missing_required_key(self):
        """Test error when required key is missing."""
        with pytest.raises(KeyError):
            MyFunction({})  # Assuming 'key' is required

# Class tests
class TestMyClass:
    """Tests for MyClass."""
    
    def test_initialization(self):
        """Test class initialization."""
        obj = MyClass(42)
        assert obj.value == 42
    
    def test_method(self):
        """Test class methods."""
        obj = MyClass(10)
        assert obj.double() == 20
```

### Running Tests

```bash
# Run all tests
pytest tests/

# Run specific file
pytest tests/test_my_module.py

# Run specific test
pytest tests/test_my_module.py::TestMyClass::test_initialization

# Run with verbose output
pytest -v tests/

# Stop on first failure
pytest -x tests/

# Show print statements
pytest -s tests/

# Run with coverage report
pytest --cov=CrocoDash tests/
```

### Test Fixtures and Mocking

For tests that need external data or network access, use mocking:

```python
from unittest.mock import patch, MagicMock
import pytest

def test_with_mock_network():
    """Test function that calls external API."""
    with patch('CrocoDash.my_module.requests.get') as mock_get:
        # Setup mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "mocked"}
        mock_get.return_value = mock_response
        
        # Call function
        result = fetch_data()
        
        # Verify
        assert result["data"] == "mocked"
        mock_get.assert_called_once()
```

## Debugging

### Using Print Statements

For quick debugging, add print statements and run tests with `-s`:

```bash
pytest -s tests/test_file.py::test_function
```

### Using the Python Debugger

Add breakpoints in your code:

```python
import pdb

def my_function():
    x = 10
    pdb.set_trace()  # Execution pauses here
    y = x + 5
    return y

# Common pdb commands:
# n - next line
# s - step into function
# c - continue execution
# p variable_name - print variable
# l - list source code
# h - help
```

### Using IDE Debugger

If using VS Code:
1. Set breakpoints by clicking on line numbers
2. Press F5 to start debugging
3. Use the debug panel to step through code

### Logging for Debugging

Use the logging module instead of print statements in production code:

```python
import logging

logger = logging.getLogger(__name__)

def my_function():
    logger.debug("Function started")
    x = expensive_computation()
    logger.info(f"Computed x = {x}")
    if x < 0:
        logger.warning("x is negative, this might be unexpected")
    return x
```

Run tests to see log output:

```bash
pytest -s --log-cli-level=DEBUG tests/test_file.py
```

## Making API Changes

### Backwards Compatibility

When modifying existing functions or classes, consider backwards compatibility:

```python
# Good: Add optional parameter with default
def my_function(x, y=None):  # y is new, optional
    if y is None:
        y = 10
    return x + y

# Acceptable: Deprecate old behavior
import warnings

def my_function(x, use_new_algorithm=True):
    if not use_new_algorithm:
        warnings.warn(
            "use_new_algorithm=False is deprecated, will be removed in v1.0",
            DeprecationWarning,
            stacklevel=2
        )
    # ... implementation
```

### Breaking Changes

If you must make breaking changes:

1. **Document clearly** in the docstring and commit message
2. **Bump version number** (semantic versioning)
3. **Update migration guide** in documentation
4. **Update tests** to reflect new behavior

### Deprecation Process

1. Add `DeprecationWarning` in version N
2. Keep functionality working for 1-2 releases
3. Remove in version N+2 or later
4. Document in release notes

## Updating Dependencies

### Adding a New Dependency

1. **Install locally:**
   ```bash
   mamba install package-name
   ```

2. **Update environment.yml:**
   ```yaml
   dependencies:
     - python=3.10
     - xarray
     - new-package-name  # Add here
   ```

3. **Ensure it's importable:**
   ```bash
   python -c "import new_package_name"
   ```

4. **Update tests** if needed

### Updating Existing Dependencies

1. **Check compatibility:**
   ```bash
   mamba update package-name
   pytest tests/
   ```

2. **Update environment.yml** version if needed

3. **Test thoroughly** before committing

## Performance Profiling

### Using cProfile

```python
import cProfile
import pstats

def my_function():
    # Code to profile
    pass

# Profile
cProfile.run('my_function()', 'stats')

# View results
stats = pstats.Stats('stats')
stats.sort_stats('cumulative')
stats.print_stats(10)  # Top 10 functions
```

### Memory Profiling

```bash
# Install memory profiler
pip install memory-profiler

# Profile a function
python -m memory_profiler script.py
```

Add decorator to function:
```python
from memory_profiler import profile

@profile
def my_function():
    pass
```

## Code Quality Checks

### Using Pre-commit Hooks

Set up automatic checks before committing:

```bash
# Install pre-commit
pip install pre-commit

# Create .pre-commit-config.yaml in repo root
# Configure desired checks
pre-commit install

# Now checks run automatically on git commit
```

### Manual Quality Checks

```bash
# Linting (if configured)
flake8 CrocoDash/

# Type checking (if using type hints)
mypy CrocoDash/

# Code style
black --check CrocoDash/

# Run all tests
pytest tests/

# Coverage report
pytest --cov=CrocoDash tests/
```

## Working with Jupyter Notebooks

For development and testing in notebooks:

```bash
# Navigate to dev folder
cd dev

# Launch Jupyter
jupyter notebook
```

Best practices:
- Use notebooks for exploratory work and documentation
- Move tested code to proper modules
- Don't commit notebooks with cell outputs unless necessary
- Use `%matplotlib inline` for visualizations
- Clear outputs before committing

## Dealing with Circular Imports

If you get circular import errors:

```python
# Bad: Import at module level
from CrocoDash.module_a import ClassA  # module_a also imports from current module

# Good: Import inside function/method
def my_function():
    from CrocoDash.module_a import ClassA
    return ClassA()

# Also good: Reorder imports/reorganize code
```

## Building and Installing Locally

For testing your changes before pushing:

```bash
# Install in development mode (editable install)
pip install -e .

# Now imports work from anywhere
python -c "from CrocoDash import Case"

# Reinstall after major changes
pip install -e . --force-reinstall
```

## Next Steps

- Read [Project Architecture](project_architecture.md) to understand module interactions
- Check [Contributing Guidelines](contributing.md) before submitting code
- Review [Adding Data Access](adding_data_access.md) for data source development
