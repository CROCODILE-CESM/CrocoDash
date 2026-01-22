# Project Architecture

## Overview

CrocoDash is organized around the workflow of setting up a regional MOM6 case within CESM. The architecture is modular, with each component handling a specific aspect of the setup process.

## Core Modules

### `case.py` - Main Case Class

The `Case` class is the entry point for most users. It represents a regional MOM6 case within the CESM framework and provides methods to:

- Initialize a new case with grid, bathymetry, and vertical grid information
- Configure forcing and boundary conditions through the `ForcingConfigRegistry`
- Setup and run the case through the CESM workflow
- Manage case I/O and configuration

**Key Methods:**
- `__init__()` - Initialize case with CESM and grid specifications
- `configure_*()` - Methods to configure different forcing and boundary condition components
- `setup()` / `build()` / `submit()` - CESM workflow control

### `forcing_configurations.py` - Forcing Configuration Framework

This module contains the framework for configuring all forcing and open boundary condition (OBC) setups. It uses a registry pattern where each forcing type (e.g., `Tides`, `BGC`, `Rivers`) is registered as a configuration class.

**Key Concepts:**
- `@register` decorator - Used to register new forcing configuration classes in `ForcingConfigRegistry`
- `ForcingConfigRegistry` - Central registry of all available forcing configurations
- Each forcing configuration class validates inputs and applies appropriate CESM/MOM6 settings
- **Validation happens here** - All options validation (e.g., "Chlorophyll cannot be provided if BGC is not in compset") should be implemented in `configure_forcings()`

**Example Registry Classes:**
- `Tides` - Handles tidal forcing configuration
- `BGC` - Biogeochemistry configuration
- `Rivers` - River nutrient and runoff configuration

### `grid.py`, `topo.py`, `vgrid.py` - Grid Objects

These modules define the grid infrastructure for a regional case:

- **`grid.py` (`Grid` class)** - Horizontal grid specification and management
- **`topo.py` (`Topo` class)** - Bathymetry/topography data
- **`vgrid.py` (`VGrid` class)** - Vertical grid specification

These are passed to the `Case` class during initialization.

### `extract_forcings/` - Forcing Extraction Module

A dedicated module that decouples forcing/OBC generation from the main `Case` workflow. This is necessary because forcing extraction is complex and computationally heavy.

**Key Components:**
- `driver.py` - Main entry point for forcing extraction
- `case_setup/` - Logic for case-specific forcing setup
- `code/` - Core forcing generation algorithms
- `utils.py` - Utility functions for forcing handling

**Responsibility:** Extract initial conditions and open boundary conditions from source datasets, regrid them, and format them for MOM6.

### `raw_data_access/` - Data Access Module

Provides unified access to all external datasets used in CrocoDash.

**Key Components:**
- `base.py` - Base class (`ForcingProduct`) that all data products inherit from
- `registry.py` - Data product registry and registry management
- `datasets/` - Individual dataset implementations (one file per data product)
- `utils.py` - Utility functions for data access and handling

**Responsibility:** Handle downloading, caching, and accessing data from various sources (MOM6 output, TPXO, GLOFAS, etc.)

### `logging.py` - Logging Configuration

Provides consistent logging setup across the package.

### `topo_editor.py` - Bathymetry Editing Tool

Provides utilities for interactive bathymetry editing (TopoEditor feature).

## Data Flow

### Case Setup Workflow

```
1. Initialize Grid, Topo, VGrid
   ↓
2. Create Case object with grid specifications
   ↓
3. Configure forcing via ForcingConfigRegistry
   ↓
4. Extract forcings via extract_forcings module
   ↓
5. Setup case via CESM/VisualCaseGen integration
   ↓
6. Build and submit case
```

### Forcing Configuration Validation

```
Raw configuration input
   ↓
ForcingConfigRegistry.configure_forcings()
   ↓
Validate all options (e.g., BGC requirements)
   ↓
Apply configurations to Case object
```

### Data Access Workflow

```
User requests data (e.g., MOM6 temperature)
   ↓
ProductRegistry.get_product()
   ↓
ForcingProduct subclass downloads/loads data
   ↓
Data is cached locally
   ↓
Data returned to user
```

## Integration with External Projects

CrocoDash integrates with several other projects:

- **[regional-mom6](https://github.com/CROCODILE-CESM/regional-mom6)** - Regional MOM6 setup and OBC generation
- **[mom6_bathy](https://github.com/NCAR/mom6_bathy)** - Bathymetry and grid tools
- **[VisualCaseGen](https://github.com/CROCODILE-CESM/VisualCaseGen)** - CESM case setup interface (ProConPy-based)
- **[CESM](https://github.com/CROCODILE-CESM/CESM)** - Community Earth System Model

## Key Design Patterns

### Registry Pattern
Both `ForcingConfigRegistry` and `ProductRegistry` use the registry pattern to allow extensibility without modifying core code. New configurations or data products can be added by creating a new class and using the `@register` decorator.

### Configuration as Code
Forcing and OBC configurations are defined as Python classes rather than static files, allowing for complex validation logic and dynamic configuration.

### Separation of Concerns
- `Case` class handles CESM case management
- `ForcingConfigRegistry` handles configuration validation
- `extract_forcings` handles heavy computational tasks
- `raw_data_access` handles external data integration

## Configuration File Structure

CrocoDash uses JSON configuration files to specify case setups. The configuration structure includes:

- **`basic`** - Basic paths and date ranges
- **`forcing`** - Forcing data product specifications
- **`tides`** - Tidal forcing configuration
- **`bgc`** - Biogeochemistry configuration
- **`bgcic`** - BGC initial conditions
- **`runoff`** - Runoff configuration
- Other component-specific sections

See the active config file in your workspace for a complete example.
