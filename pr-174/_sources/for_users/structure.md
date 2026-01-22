# Understanding CrocoDash's Structure

CrocoDash manages the complete workflow from raw data sources to a fully configured regional MOM6 case within CESM. The package is organized into three main phases:

## 1. Grid Generation

CrocoDash wraps the `mom6_bathy` module to generate the horizontal and vertical grids:

- **Supergrid** - Structured Arakawa C-grid (via `Grid` class)
- **Vertical Grid** - Depth levels and layer thickness (via `VGrid` class)
- **Bathymetry/Topography** - Bathyemtry setting (via `Topo` class)

Key features:
- `TopoEditor` - Interactive bathymetry editing tool

**Modules:** `CrocoDash.grid`, `CrocoDash.vgrid`, `CrocoDash.topo`, `CrocoDash.topo_editor`

## 2. Case Setup (CESM Interface)

CrocoDash wraps `VisualCaseGen` to create and configure CESM cases:

- **Case Initialization** - Creates the case directory structure
- **Component Setup** - Configures atmosphere, ocean, land, ice, runoff components
- **Grid Registration** - Links your custom MOM6 grid to the case
- **Configuration** - Sets compset, machine, queue, and other case options

Key features:
- `Case` class - Main entry point for case creation and configuration
- `ForcingConfigRegistry` - Manages all forcing and boundary condition configurations
- Integration with CESM's xmlchange and user_nl system

**Module:** `CrocoDash.case`, `CrocoDash.forcing_configurations`

## 3. Forcing File Generation

CrocoDash uses the `extract_forcings` module to generate forcings from source datasets:

- **Data Access** - Unified interface to multiple forcing datasets (MOM6, TPXO, GLOFAS, etc.)
- **Regridding** - Maps data from source grids to your custom regional grid
- **Format Conversion** - Converts data to MOM6-compatible file formats
- **Boundary Extraction** - Extracts OBC data for domain boundaries (north, south, east, west)

Key features:
- `raw_data_access` module - Access various datasets programmatically
- `extract_forcings` - Decoupled from main Case workflow for heavy computation
- Configuration serialization - Stores setup in JSON for reproducibility

**Module:** `CrocoDash.extract_forcings`, `CrocoDash.raw_data_access`

## Workflow Overview

```
1. Define Grid (horizontal & vertical)
   ↓
2. Define Bathymetry
   ↓
3. Create Case Object with grids
   ↓
4. Configure Forcing (validate compset, set options)
   ↓
5. Process Forcings (download, regrid, format data)
   ↓
6. Build Case (case.build())
   ↓
7. Submit Case (case.submit())
```

## Key Classes

### Core Case Management
- **`Case`** - Main class representing a regional MOM6 case
  - Manages grid, bathymetry, vertical grid
  - Coordinates configuration, setup, build, submit
  - Integrates with CESM workflow

### Grid Objects
- **`Grid`** - Horizontal grid specification
- **`VGrid`** - Vertical grid specification  
- **`Topo`** - Bathymetry data

### Configuration
- **`BaseConfigurator`** - Base class for all forcing configurations
- **`ForcingConfigRegistry`** - Registry managing all configurations
- **Specific Configurators** - TidesConfigurator, BGCConfigurator, RiverNutrientsConfigurator, etc.

### Data Access
- **`ForcingProduct`** - Base class for data access implementations
- **`raw_data_access.registry`** - Registry of available datasets
- **`raw_data_access.datasets`** - Individual dataset implementations


## Integration with External Tools

CrocoDash ties together several specialized tools:

- **[mom6_bathy](https://github.com/NCAR/mom6_bathy)** - Grid generation and bathymetry tools
- **[regional-mom6](https://github.com/COSIMA/regional-mom6)** - Regional MOM6 setup and OBC generation
- **[VisualCaseGen](https://github.com/ESMCI/VisualCaseGen)** - CESM case creation GUI framework (ProConPy-based)
- **[CESM](https://github.com/ESCOMP/CESM)** - Community Earth System Model

These are included as submodules in the CrocoDash repository.

## For Developers

For a detailed understanding of CrocoDash architecture:
- See [Project Architecture](../for_developers/project_architecture.md) in the developer documentation
- Understand the [Forcing Configuration Framework](../for_developers/adding_forcing_configurations.md) for extending configurations
- Check [Development Information](../for_developers/dev_info.md) to start contributing

