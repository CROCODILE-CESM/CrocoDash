# Contributing Guidelines

Thank you for contributing to CrocoDash! This document provides guidelines for contributing code, documentation, and other improvements.

## Before You Start

1. Check existing [issues](https://github.com/CROCODILE-CESM/CrocoDash/issues) and [pull requests](https://github.com/CROCODILE-CESM/CrocoDash/pulls) to avoid duplicate work
2. For major features, consider opening an issue first to discuss the approach
3. Read the [Project Architecture](project_architecture.md) to understand the codebase
4. Set up your [development environment](dev_environment.md)

## Code Style and Standards

### Python Code Style

CrocoDash follows Python best practices and PEP 8 conventions:

- **Line length:** 88 characters (configured for Black formatter)
- **Indentation:** 4 spaces
- **Imports:** Use absolute imports
- **Naming:** 
  - Functions/variables: `lowercase_with_underscores`
  - Classes: `PascalCase`
  - Constants: `UPPERCASE_WITH_UNDERSCORES`
  - Private members: prefix with `_`

### Code Quality Tools

While not strictly enforced in all cases, the following tools are recommended:

```bash
# Code formatting (if used)
black CrocoDash/
```

### Docstrings

All public functions, classes, and modules must have docstrings following the NumPy docstring format:

```python
def calculate_mean(data: list[float], weighted: bool = False) -> float:
    """
    Calculate the mean of data.
    
    Longer description goes here. Explain what the function does,
    including important details or edge cases.
    
    Parameters
    ----------
    data : list[float]
        Input data values
    weighted : bool, optional
        If True, weight values by their position. Default is False.
        
    Returns
    -------
    float
        The calculated mean
        
    Raises
    ------
    ValueError
        If data is empty
        
    See Also
    --------
    numpy.mean : NumPy mean function
    
    Examples
    --------
    >>> calculate_mean([1, 2, 3])
    2.0
    >>> calculate_mean([1, 2, 3], weighted=True)
    2.25
    """
    if not data:
        raise ValueError("data cannot be empty")
    return sum(data) / len(data)

class CaseAnalyzer:
    """Analyze CESM case output.
    
    This class provides methods to analyze and summarize the output
    from CESM regional MOM6 cases.
    
    Attributes
    ----------
    case_path : Path
        Path to the case directory
    results : dict
        Dictionary containing analysis results
    """
    
    def __init__(self, case_path: str | Path):
        """
        Initialize CaseAnalyzer.
        
        Parameters
        ----------
        case_path : str | Path
            Path to the case directory
        """
        self.case_path = Path(case_path)
        self.results = {}
```

### Type Hints

Use type hints for clarity (especially for public APIs):

```python
from pathlib import Path
from typing import Optional, Dict, Tuple
import xarray as xr

def process_data(
    input_file: str | Path,
    output_dir: str | Path,
    verbose: bool = False,
    options: Optional[Dict[str, str]] = None
) -> xr.Dataset:
    """Process data with optional configuration."""
    pass

def get_bounds(data: xr.Dataset) -> Tuple[float, float, float, float]:
    """Return (lat_min, lat_max, lon_min, lon_max)."""
    pass
```

## Making Changes

### 1. Create a Feature Branch

```bash
git checkout -b feature/description-of-feature
# or
git checkout -b fix/description-of-bugfix
# or
git checkout -b docs/description-of-documentation
```


### 2. Write Tests

All code changes should include tests.

```bash
# Run tests before submitting PR
pytest tests/ -v

```

Aim for:
- **New code:** 80%+ coverage
- **Modified code:** Coverage should not decrease
- **Test organization:** Group related tests in modules

### 4. Update Documentation

If your change affects user-facing functionality:

1. Update docstrings
2. Update relevant documentation files in `docs/source/`
3. Add examples if helpful
4. Update API docs if necessary:
   ```bash
   cd docs
   sphinx-apidoc -o source/api-docs ../CrocoDash
   ```

### 5. Test Documentation Build

```bash
cd docs
make clean
make html
```

Check that:
- Build succeeds without errors
- New documentation appears where expected
- Cross-references work correctly

## Submitting a Pull Request

### PR Title and Description

Use a clear, descriptive title:
```
Add validation for BGC forcing configuration
```

In the description, explain:
- **What** you're changing and why
- **How** you're making the change
- **Any breaking changes** or important notes
- **How to test** the changes (if not obvious)
- **Related issues** (use `Fixes #123` syntax)

**Example PR description:**
```markdown
## Summary
Add comprehensive validation for BGC forcing configurations to prevent 
configuration errors early in the workflow.

## Changes
- Add `validate_bgc_config()` method to `BGCConfig` class
- Check that BGC tracers are only specified when BGC is in compset
- Validate tracer dependencies and variable mappings
- Add 15 new tests covering validation edge cases

## Breaking Changes
None

## Testing
- All existing tests pass
- New tests cover: valid configs, missing required fields, invalid tracer combinations
- Tested with sample config files from workshop cases

## Related Issues
Fixes #145

## Checklist
- [x] Tests added/updated
- [x] Documentation updated
- [x] Docstrings added/updated
- [x] No breaking changes (or documented)
```

### PR Checklist

Before submitting, ensure:

- [ ] **Tests written and passing**
  ```bash
  pytest tests/ -v
  ```

- [ ] **Code follows style guidelines**
  - Docstrings added/updated
  - Type hints included (where appropriate)
  - No obvious style violations

- [ ] **Documentation updated**
  - Relevant docs updated
  - Code examples added/updated
  - API docs regenerated (if needed)

- [ ] **No unrelated changes**
  - One feature/fix per PR
  - No formatting-only changes (unless separate PR)

- [ ] **Branch is up-to-date**
  ```bash
  git fetch origin
  git rebase origin/main
  ```

## Merging

Once approved:

1. Ensure all CI checks pass
2. Squash or rebase commits if needed for clean history
3. Merge to `main` branch

Typically, you should handle merging once approved.

## Reporting Issues

### Good Issue Report

Include:
- **Title:** Clear, descriptive
- **Description:** What happened and what you expected?
- **Steps to reproduce:** How to reproduce the issue
- **Environment:** OS, Python version, package versions
- **Error message:** Full traceback if applicable
- **Additional context:** Screenshots, data files, etc.

## Getting Help

- **GitHub Issues:** For bugs and feature requests
- **GitHub Discussions:** For questions and ideas
- **Code comments:** In pull reviews for technical questions
- **Email:** Contact maintainers directly for sensitive issues

## License and Attribution

By contributing to CrocoDash, you agree that your contributions will be licensed under the same license as the project. See LICENSE file in the repository.

Significant contributions will be acknowledged in:
- CONTRIBUTORS file
- Release notes
- Documentation credits

## Recognition and Appreciation

All contributors are valued! We appreciate:
- Code contributions
- Bug reports and testing
- Documentation and tutorials
- Help with issues and discussions
- Feature ideas and feedback

Thank you for making CrocoDash better!

