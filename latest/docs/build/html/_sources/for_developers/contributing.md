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
- **Imports:** Use absolute imports; group standard library, third-party, and local imports
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

# Linting (static analysis)
flake8 CrocoDash/

# Type checking (if using type hints)
mypy CrocoDash/
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

Branch naming conventions:
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `refactor/` - Code refactoring
- `test/` - Test additions/improvements

### 2. Make Your Changes

- Keep commits atomic and focused
- Write clear, descriptive commit messages
- Reference issues where applicable (e.g., "Fixes #123")

**Good commit message:**
```
Add BGC validation to forcing configurations

- Validate that BGC tracers only provided when BGC in compset
- Add checks for tracer dependencies
- Include tests for validation logic

Fixes #145
```

**Avoid:**
```
update code
fixed stuff
```

### 3. Write Tests

All code changes should include tests. See [Common Development Tasks](common_dev_tasks.md#writing-tests) for details.

```bash
# Run tests before submitting PR
pytest tests/ -v

# Check coverage
pytest tests/ --cov=CrocoDash
```

Aim for:
- **New code:** 80%+ coverage
- **Modified code:** Coverage should not decrease
- **Test organization:** Group related tests in classes

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

- [ ] **Commits are clean**
  - Atomic, focused commits
  - Clear commit messages
  - No merge commits or accidental changes

- [ ] **No unrelated changes**
  - One feature/fix per PR
  - No formatting-only changes (unless separate PR)

- [ ] **Branch is up-to-date**
  ```bash
  git fetch origin
  git rebase origin/main
  ```

## Code Review Process

### What Reviewers Look For

- **Correctness:** Does the code do what it's supposed to?
- **Design:** Does it fit with the existing architecture?
- **Tests:** Are edge cases and error conditions tested?
- **Documentation:** Are changes documented clearly?
- **Style:** Does it follow project conventions?

### Responding to Feedback

- **Be respectful** - Code review is collaborative
- **Respond to all comments** - Either make requested changes or explain why not
- **Ask questions** - If feedback is unclear, ask for clarification
- **Update commits** - Use git fixup/rebase to keep history clean:
  ```bash
  # Make changes
  git add .
  git commit --fixup <commit-hash>
  
  # Rebase to squash fixup commits
  git rebase -i origin/main
  # Mark fixup commits as 'fixup'
  ```

## Merging

Once approved:

1. Ensure all CI checks pass
2. Squash or rebase commits if needed for clean history
3. Merge to `main` branch

Typically, maintainers handle merging, but if you have merge permissions:

```bash
git checkout main
git pull origin main
git merge --squash feature/my-feature
git commit
git push origin main
```

## Reporting Issues

### Good Issue Report

Include:
- **Title:** Clear, descriptive
- **Description:** What happened and what you expected?
- **Steps to reproduce:** How to reproduce the issue
- **Environment:** OS, Python version, package versions
- **Error message:** Full traceback if applicable
- **Additional context:** Screenshots, data files, etc.

**Example:**
```markdown
## Title: Grid coordinates incorrect when lat/lon cross -180/180

## Description
When setting up a case with a domain that crosses the -180/180 boundary,
grid coordinates are incorrectly transformed.

## Steps to Reproduce
1. Create grid with lon bounds: [170, -170] (crosses dateline)
2. Initialize Case with this grid
3. Check grid.lon_2d values

## Expected Behavior
Grid coordinates should be continuous across dateline.

## Actual Behavior
Grid coordinates have a discontinuity at the boundary.

## Environment
- OS: Linux (GLADE)
- Python: 3.10
- CrocoDash: 0.1.0-beta
- xarray: 2023.01.0

## Error Message
(Full traceback if applicable)

## Additional Context
Similar to issue #89 but for regional grids.
```

## Getting Help

- **GitHub Issues:** For bugs and feature requests
- **GitHub Discussions:** For questions and ideas
- **Code comments:** In pull reviews for technical questions
- **Email:** Contact maintainers directly for sensitive issues

## License and Attribution

By contributing to CrocoDash, you agree that your contributions will be licensed under the same license as the project (typically MIT or Apache 2.0). See LICENSE file in the repository.

Significant contributions will be acknowledged in:
- CONTRIBUTORS file (if maintained)
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

## Additional Resources

- [Project Architecture](project_architecture.md)
- [Development Environment Setup](dev_environment.md)
- [Common Development Tasks](common_dev_tasks.md)
- [Adding Data Sources](adding_data_access.md)
- [Writing Documentation](docs.md)
- [CROCODILE Project](https://github.com/CROCODILE-CESM)
