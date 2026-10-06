# Adding Forcing Configurations

This guide explains how to add a new forcing configuration to CrocoDash. Forcing configurations handle the setup of different components like tides, biogeochemistry, rivers, and more.

## Overview

The forcing configuration framework in the `CrocoDash.forcing` package (`forcing/base.py`) uses a declarative, registry-based approach:

- **`BaseConfigurator`** - Abstract base class that all forcing configurations inherit from
- **`@register` decorator** - Automatically registers configurators in `ForcingConfigRegistry`
- **Input/Output Parameters** - Declarative metadata that describe what data a configurator needs and what case parameters it modifies

The workflow is:
1. User provides compset and configuration inputs (dates, file paths, options)
2. `ForcingConfigRegistry` validates and instantiates active configurators based on compset
3. Each configurator processes user and case inputs and generates outputs (xmlchange, user_nl modifications)
4. Configuration is serialized to `config.json`
5. `crocodash process` / `run_workflow()` reads that JSON back and calls each
   configurator's `process_*` method

## Step 1: Create Your Configurator Class

Inherit from `BaseConfigurator`:

```python
from CrocoDash.forcing.base import (
    BaseConfigurator,
    register,
    InputFileParam,
    InputValueParam,
    UserNLConfigParam,
    XMLConfigParam,
    ConfigOutputParam,
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
        # Values injected from the Case object are still input params -- they
        # must be declared here or __init__ will raise "Unexpected inputs".
        InputValueParam("case_inputdir", comment="Case input directory"),
    ]
```

**Parameter Types:**

- **`InputValueParam`** - Simple values (strings, numbers, booleans)
- **`InputFileParam`** - File paths (automatically validated as existing files)

:::{important}
`BaseConfigurator.__init__` calls `validate_args()`, which requires the set of
keyword arguments you pass to `super().__init__()` to **exactly** match the set
of declared `input_params` names — no missing entries, no extras. That includes
`case_`-prefixed arguments: they are injected by the registry rather than by the
user, but they are still ordinary input params and must be declared. Forgetting
one raises `ValueError: Unexpected inputs: {'case_inputdir'}`.
:::

**Important:** Input parameters must be **JSON serializable**. They're serialized into `config.json` so the processing step can rebuild the configurator for heavy computational work.

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
- **`ConfigOutputParam`** - A derived value with **no** case-side effect: not
  `xmlchange`'d, not written to `user_nl_*`. It exists so `set_output_param()`
  and `serialize()` pick the value up into `config.json`, for values consumed
  only at process time (by your own `process_*` method, or a sibling's).

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
        super().configure()
```

:::{warning}
End `configure()` with `super().configure()` rather than looping over
`self.output_params` and calling `param.apply()` yourself. The base
implementation propagates the case's `is_non_local` flag onto every
`XMLConfigParam` before applying it; a hand-rolled loop skips that and issues
`xmlchange` without `--non-local`, which silently writes to the wrong place on a
non-local case.
:::

## Step 5b: Declare a Process Step (if your forcing generates files)

`configure()` only touches the case. If your configurator also has work to do at
*processing* time — downloading, regridding, writing netCDF — declare it in
`process_components`, mapping a CLI flag name onto a method name:

```python
@register
class MyConfigurator(BaseConfigurator):
    name = "my_component"
    process_components = {"mycomponent": "process"}

    def process(self, ctx):
        """Generate this forcing's files. `ctx` is the WorkflowContext."""
        ...
```

This is what wires you into the workflow:

- `crocodash process` grows a `--mycomponent` flag automatically
  (`cli.py` builds its flag list from `ForcingConfigRegistry.all_process_flags()`)
- `--all` and `--skip` pick it up with no further changes
- `forcing/driver.py` dispatches to it via
  `ForcingConfigRegistry.resolve_process_targets()`

A configurator that only sets namelist defaults leaves `process_components`
empty. One whose forcing type is one-to-many declares more than one entry —
`ConditionsConfigurator` uses `{"ic": "process_ic", "bc": "process_bc"}`.

If your `process_*` method needs a value another configurator computed, declare
that coupling in `depends_on_outputs` rather than reaching into
`ctx.config[...]` directly:

```python
    depends_on_outputs = {"conditions": ["date_format"]}
```

Processing may run in a different process than `configure()`, so the value comes
back through `config.json` via
`ForcingConfigRegistry.get_configurator_output()`. Declaring it lets `driver.py`
derive processing order automatically, and lets a test statically confirm the
named output actually exists on the target class.

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
from CrocoDash.forcing.base import (
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
    allowed_compsets = ["CICE"]
    forbidden_compsets = []
    process_components = {"iceforcing": "process"}

    input_params = [
        InputFileParam(
            "ice_data_file",
            comment="Path to ice initial conditions"
        ),
        InputValueParam(
            "ice_concentration_threshold",
            comment="Minimum ice concentration to include"
        ),
        # Injected by the registry from the Case -- still must be declared.
        InputValueParam(
            "case_inputdir",
            comment="Case input directory"
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
        except (TypeError, ValueError):
            raise ValueError(
                f"ice_concentration_threshold must be numeric, "
                f"got {ice_concentration_threshold!r}"
            )
        if not (0 <= threshold <= 1):
            raise ValueError("Threshold must be between 0 and 1")

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

        # Set outputs, then let the base class apply them
        self.set_output_param("ICE_DATA_FILE", data_file)
        self.set_output_param("ice_conc_min", threshold)
        super().configure()

    def process(self, ctx):
        """Generate the ice forcing file (runs under `crocodash process`)."""
        ...
```

Three details in that example are easy to get wrong, and all three are checked
at runtime:

1. `case_inputdir` appears in **both** `input_params` and `__init__`.
2. `configure()` ends with `super().configure()`, not a manual `apply()` loop.
3. The bare `except ValueError` around `float(...)` would otherwise also swallow
   the "must be between 0 and 1" error and re-raise it with a misleading
   message, so the range check sits outside the `try`.

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

Validation should happen in `validate_args`, which is called from the base
`__init__`. Always call `super().validate_args(**kwargs)` first — the base
implementation is what enforces that your declared `input_params` and the
constructor kwargs line up. Dropping it silently disables that check:

```python
def validate_args(self, **kwargs):
    super().validate_args(**kwargs)
    assert kwargs["my_required_param"] is not None
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

Available case attributes are whatever objects are on the Case object. Remember
that each one must also be declared in `input_params` (see Step 2).

A configurator can also check whether a *sibling* configurator is active through
`self.registry`, which `ForcingConfigRegistry` injects after all active
configurators are instantiated:

```python
if self.registry.is_active("tides"):
    ...
```

## Testing Your Configurator

Most basic testing is taken care of, and the registry will run available configurators. Only add additional tests if your configurator has unique configure/method behavior.

## See Also

- [Architecture](architecture.md) — how `CrocoDash.forcing` fits into the rest of CrocoDash
- [Submodule API Usage](submodule_api_usage.md) — external entry points used by configurators
- Example implementations in `CrocoDash/forcing/` (`tides.py`, `chl.py`, `runoff.py`, `bgc.py`, `mom6.py`)
