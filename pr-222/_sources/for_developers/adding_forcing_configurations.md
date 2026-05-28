# Adding Forcing Configurations

This guide explains how to add a new forcing configuration to CrocoDash. Forcing configurations handle the setup of different components like tides, biogeochemistry, rivers, and more.

## Overview

The forcing configuration framework in `forcing_configurations.py` uses a declarative, registry-based approach:

- **`BaseConfigurator`** - Abstract base class that all forcing configurations inherit from
- **`@register` decorator** - Automatically registers configurators in `ForcingConfigRegistry`
- **Input/Output Parameters** - Declarative metadata that describe what data a configurator needs and what case parameters it modifies

The workflow is:
1. User provides compset and configuration inputs (dates, file paths, options)
2. `ForcingConfigRegistry` validates and instantiates active configurators based on compset
3. Each configurator processes user and case inputs and generates outputs (xmlchange, user_nl modifications)
4. Configuration is serialized to JSON for use by `extract_forcings` module

## Step 1: Create Your Configurator Class

Inherit from `BaseConfigurator`:

```python
from CrocoDash.forcing_configurations import (
    BaseConfigurator,
    register,
    InputFileParam,
    InputValueParam,
    UserNLConfigParam,
    XMLConfigParam,
)

@register
class MyConfigurator(BaseConfigurator):
    """Configure MyComponent for the case."""
    
    name = "my_component"
    required_for_compsets = []  # e.g., ["BGC"] means required if "BGC" in compset
    allowed_compsets = []       # e.g., ["MOM6"] means only allowed if "MOM6" in compset
    forbidden_compsets = []     # e.g., ["CICE"] means incompatible if "CICE" in compset
```

The decorator automatically registers your class in `ForcingConfigRegistry.registered_types`.

## Step 2: Define Input Parameters

Declare what inputs your configurator needs as class variables:

```python
@register
class MyConfigurator(BaseConfigurator):
    name = "my_component"
    
    input_params = [
        InputFileParam(
            "data_filepath",
            comment="Path to input data file"
        ),
        InputValueParam(
            "processing_mode",
            comment="How to process data: 'fast' or 'accurate'"
        ),
    ]
```

**Parameter Types:**

- **`InputValueParam`** - Simple values (strings, numbers, booleans)
- **`InputFileParam`** - File paths (automatically validated as existing files)

**Important:** Input parameters must be **JSON serializable**. They're serialized to pass configuration to the `extract_forcings` module for heavy computational work.

## Step 3: Define Output Parameters

Declare what CESM/MOM6 case parameters this configurator will modify:

```python
@register
class MyConfigurator(BaseConfigurator):
    name = "my_component"
    
    input_params = [...]
    
    output_params = [
        XMLConfigParam(
            "MY_COMPONENT_ENABLED",
            is_non_local=False,
            comment="Enable MyComponent"
        ),
        UserNLConfigParam(
            "my_component_data_file",
            user_nl_name="mom",
            comment="Path to component data in user_nl_mom"
        ),
    ]
```

**Parameter Types:**

- **`XMLConfigParam`** - CESM XML configuration (applied via `xmlchange`)
  - `is_non_local=False` for regular XML settings
  - `is_non_local=True` for non-local settings (experiment-specific)
- **`UserNLConfigParam`** - Namelist parameters (written to `user_nl_<component>` files)
  - `user_nl_name` specifies which component file (default: "mom")

## Step 4: Implement the `__init__` Method

Define what inputs your configurator accepts:

```python
@register
class MyConfigurator(BaseConfigurator):
    name = "my_component"
    input_params = [...]
    output_params = [...]
    
    def __init__(
        self,
        data_filepath: str,
        processing_mode: str,
        case_caseroot: str = None,  # Optional: access Case object attributes
        case_inputdir: str = None,
    ):
        """
        Initialize configurator.
        
        Parameters
        ----------
        data_filepath : str
            Path to input data file
        processing_mode : str
            Processing mode: 'fast' or 'accurate'
        case_caseroot : str, optional
            Case root directory (passed from Case object)
        case_inputdir : str, optional
            Case input directory (passed from Case object)
        """
        # Validate inputs before passing to parent
        if processing_mode not in ["fast", "accurate"]:
            raise ValueError(f"Unknown processing_mode: {processing_mode}")
        
        # Call parent constructor (handles input parameter binding)
        super().__init__(
            data_filepath=data_filepath,
            processing_mode=processing_mode,
            case_caseroot=case_caseroot,
            case_inputdir=case_inputdir,
        )
```

**Key Points:**

- `__init__` parameters must somehow fill `input_params` names
- Parameters starting with `case_` come from the `Case` object, the registry automatically injects these
- Other parameters are user-provided and required unless you have defaults
- Call `super().__init__(**kwargs)` to let the framework handle parameter binding

## Step 5: Implement the `configure` Method

This method processes inputs and sets output parameter values:

```python
@register
class MyConfigurator(BaseConfigurator):
    # ... class variables and __init__ ...
    
    def configure(self):
        """Process inputs and set output parameters."""
        # Access input values via attribute access
        data_file = self.data_filepath  # Accesses input parameter
        mode = self.processing_mode
        
        # Process/validate
        if not Path(data_file).exists():
            raise FileNotFoundError(f"Data file not found: {data_file}")
        
        # Set output parameter values
        self.set_output_param("MY_COMPONENT_ENABLED", "true")
        self.set_output_param("my_component_data_file", str(data_file))
        
        # Apply all output parameters (writes to case)
        for param in self.output_params:
            param.apply()
```

## Step 6: Add Compset Compatibility Logic (Optional)

Define when your configurator is required or allowed:

```python
@register
class MyConfigurator(BaseConfigurator):
    name = "my_component"
    required_for_compsets = ["MY_COMPONENT"]  # Required if compset contains "MY_COMPONENT"
    allowed_compsets = ["MOM6"]               # Only allowed if "MOM6" in compset
    forbidden_compsets = ["CICE"]             # Never allowed if "CICE" in compset
    
    # ... rest of class ...
```

The registry uses these to:
- **`required_for_compsets`** - Throw error if compset matches but inputs are missing
- **`allowed_compsets`** - Skip if compset doesn't match all listed strings
- **`forbidden_compsets`** - Skip if compset matches any forbidden string

## Complete Example

Here's a complete example of adding a simple configurator:

```python
from pathlib import Path
from CrocoDash.forcing_configurations import (
    BaseConfigurator,
    register,
    InputFileParam,
    InputValueParam,
    UserNLConfigParam,
    XMLConfigParam,
)

@register
class IceForcing(BaseConfigurator):
    """Configure ice boundary conditions."""
    
    name = "ice_forcing"
    required_for_compsets = []
    allowed_compsets = ["SICE"]
    forbidden_compsets = []
    
    input_params = [
        InputFileParam(
            "ice_data_file",
            comment="Path to ice initial conditions"
        ),
        InputValueParam(
            "ice_concentration_threshold",
            comment="Minimum ice concentration to include"
        ),
    ]
    
    output_params = [
        XMLConfigParam(
            "ICE_DATA_FILE",
            comment="Ice data location in case"
        ),
        UserNLConfigParam(
            "ice_conc_min",
            user_nl_name="cice",
            comment="Ice concentration threshold"
        ),
    ]
    
    def __init__(
        self,
        ice_data_file: str,
        ice_concentration_threshold: str,
        case_inputdir: str = None,
    ):
        """Initialize ice forcing configurator."""
        # Validate
        try:
            threshold = float(ice_concentration_threshold)
            if not (0 <= threshold <= 1):
                raise ValueError("Threshold must be between 0 and 1")
        except ValueError as e:
            raise ValueError(f"Invalid ice_concentration_threshold: {e}")
        
        super().__init__(
            ice_data_file=ice_data_file,
            ice_concentration_threshold=ice_concentration_threshold,
            case_inputdir=case_inputdir,
        )
    
    def configure(self):
        """Configure ice boundary conditions."""
        data_file = self.ice_data_file
        threshold = self.ice_concentration_threshold
        
        # Validate file exists
        if not Path(data_file).exists():
            raise FileNotFoundError(f"Ice data file not found: {data_file}")
        
        # Copy to case input directory if provided
        if self.case_inputdir:
            dest = Path(self.case_inputdir) / Path(data_file).name
            import shutil
            shutil.copy(data_file, dest)
            data_file = str(dest)
        
        # Set outputs and apply
        self.set_output_param("ICE_DATA_FILE", data_file)
        self.set_output_param("ice_conc_min", threshold)
        
        for param in self.output_params:
            param.apply()
```

## Important Considerations

### JSON Serialization

Input and output parameters are serialized to JSON for the `extract_forcings` module:

```python
# ✅ Good - JSON serializable
input_params = [
    InputFileParam("file_path"),           # str
    InputValueParam("threshold"),           # str
]

# ❌ Bad - Not JSON serializable
input_params = [
    InputFileParam("data_object"),          # xarray.Dataset
    InputFileParam("case_object"),          # Case instance
]
```

If you need to pass complex objects to `extract_forcings`, store serializable references (paths, identifiers) instead.

### Validation Strategy

Validation should happen in `validate_args`, which is called from the base __init__:

```python
def validate_args(self, kwargs):
    assert kwargs["true"]
```

### Accessing Case Information

To access Case object attributes, use the `case_` prefix:

```python
def __init__(self, some_param: str, case_caseroot: str = None, case_compset: str = None):
    # case_caseroot and case_compset are optional
    # They're injected by ForcingConfigRegistry if available
    super().__init__(
        some_param=some_param,
        case_caseroot=case_caseroot,
        case_compset=case_compset,
    )
```

Available case attributes are whatever objects are on the Case object.

## Testing Your Configurator

Most basic testing is taken care of, and the registry will run available configurators. Only add additional tests if your configurator has unique configure/method behavior.

## See Also

- [Project Architecture](../for_users/structure.md) - Understanding the Case class and workflow
- Example implementations in `CrocoDash/forcing_configurations.py`