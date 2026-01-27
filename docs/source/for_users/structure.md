# How CrocoDash Is Organized

CrocoDash manages the complete workflow from raw data sources to a fully configured regional MOM6 case within CESM. Understanding its structure helps you know where to find information, what each piece does, and how to extend it for your needs.

## The Three Phases of CrocoDash

Everything in CrocoDash revolves around three main phases that happen sequentially:

### Phase 1: Grid Definition

Before you can set up a case, you need to define the spatial domain. CrocoDash uses three grid objects to represent your domain:

- **Horizontal Grid** (`Grid` class) - Your Arakawa C-grid specification (lat/lon coordinates, resolution, etc.)
- **Vertical Grid** (`VGrid` class) - Depth levels and layer thickness for your domain
- **Bathymetry/Topography** (`Topo` class) - Seafloor depths and land mask

These classes are from `mom6_bathy`, and mom6_bathy provides an **interactive bathymetry editor** if you want to manually adjust seafloor features before setting up your case.

### Phase 2: Case Setup

Once you have grids defined, you create a `Case` object that represents your simulation. This phase:

- Creates the case directory structure in CESM
- Configures all model components (atmosphere, ocean, land, ice, runoff)
- Registers your custom MOM6 grid with CESM
- Sets options like compset, machine, queue, and other parameters

The `Case` class is your main entry point for all case operations. It handles coordination with CESM behind the scenes using `VisualCaseGen` and CESM's native configuration system.

### Phase 3: Forcing and Boundary Conditions

The final phase generates all the data files your simulation needs:

- **Data Access** - Retrieves raw data from multiple sources (MOM6 output, TPXO tides, GLOFAS runoff, etc.) through a unified interface
- **Regridding** - Maps data from source grids onto your custom regional grid
- **Format Conversion** - Converts data to MOM6-compatible file formats
- **Boundary Extraction** - Extracts open boundary conditions (OBC) for your domain edges (This is part of regridding)

The actual processing is decoupled from the main Case workflow because it's computationally intensive. You configure what you want in Phase 2, then CrocoDash handles the heavy lifting separately through the `extract_forcings` module.

## The Complete Workflow

Here's how you move through these phases in practice:

```
1. Define Grid (horizontal & vertical)
   ↓
2. Define Bathymetry
   ↓
3. Create Case Object with grids
   ↓
4. Configure Forcing (specify what data you want)
   ↓
5. Process Forcings (download, regrid, format)
   ↓
6. Build Case
   ↓
7. Submit Case
```

## How CrocoDash Organizes Its Code

CrocoDash is structured so that each major task has its own module. Understanding this organization helps you know where to look when you need something:

### Grid and Geometry Handling
- **`grid`, `vgrid`, `topo`** - Define and manage your horizontal grid, vertical grid, and bathymetry
- **`topo_editor`** - Interactive tool for editing bathymetry before case creation

### Case Management
- **`case`** - The main `Case` class that orchestrates everything
- **`forcing_configurations`** - Where you specify what forcing data your case needs. This module is "under-the-hood" of the configure_forcings function.

### Data Processing
- **`extract_forcings`** - The computational engine that generates all your forcing and boundary condition files
- **`raw_data_access`** - Unified interface to get data from many different sources

### Supporting Infrastructure
- **`logging`** - Consistent logging setup across the package

## The Forcing Configuration Registry

One key design pattern you'll encounter is the **configuration registry**. Instead of editing configuration files by hand, CrocoDash uses Python classes to represent each type of forcing configuration (Tides, Biogeochemistry, Rivers, etc.).

Why this approach? Because configurations aren't just data—they involve validation logic. For example, "you can't use BGC without the BGC component in your compset." By using Python classes, CrocoDash can enforce these rules automatically and give you helpful error messages if something doesn't make sense.

This also makes CrocoDash extensible: if you want to add a new forcing type, [you can create a new configuration class and register it](../for_developers/adding_forcing_configurations.md).
## The Data Access Registry

Similarly, CrocoDash provides a **data registry** that lets you access different datasets through a common interface. Under the hood, each dataset (MOM6, TPXO, GLOFAS) has its own implementation for downloading, caching, and loading data. But from your perspective, you just ask for the data you need and CrocoDash handles the details.

This design makes it easy to:
- Add support for new datasets without changing core code [(which you can do!)](../for_developers/adding_data_access.md)
- Swap out data sources if you want to use a different provider
- Cache data locally to avoid repeated downloads

## Data Flow: Case Setup to Forcing Generation

Here's a detailed view of what happens at each step:

```
1. Initialize Grid, Topo, VGrid objects
   ↓
2. Create Case object with grid specifications and input/run folders
   ↓
3. Setup case via CESM integration (creates case directories)
   ↓
4. Configure forcing via the ForcingConfigRegistry from forcing_configurations.base:
   - Specifies what datasets and configurations you want
   - Validates that your choices are compatible
   - Stores configuration in a JSON file for reproducibility
   ↓
5. Process forcings:
   - raw_data_access gets data from sources (downloads if needed)
   - extract_forcings regrids and reformats data
   - Output files are placed in your input directories
   ↓
6. Build and submit case from CESM
```

## Key Objects You'll Interact With

These are the main classes you'll use when working with CrocoDash:

- **`Case`** - Represents your simulation. You create one, configure it, then build and submit it.
- **`Grid`** - Your horizontal grid specification
- **`VGrid`** - Your vertical grid specification  
- **`Topo`** - Your bathymetry data
- **Forcing Configurators** - Objects representing Tides, Biogeochemistry, Rivers, etc. that you specify in your case

## Integration with External Tools

CrocoDash doesn't do everything itself—it orchestrates several specialized tools:

- **[mom6_bathy](https://github.com/NCAR/mom6_bathy)** - Grid generation and bathymetry tools
- **[regional-mom6](https://github.com/COSIMA/regional-mom6)** - Regional MOM6 setup and OBC generation
- **[VisualCaseGen](https://github.com/ESMCI/VisualCaseGen)** - CESM case creation interface

These are included as submodules in the CrocoDash repository, so you have everything you need in one place.

## Design Philosophy: Separation of Concerns

CrocoDash separates tasks into focused modules so you can understand and work with each piece independently:

- The **`Case` class** handles CESM case management—you don't need to know the internals of CESM to use it
- The **`forcing_configurations`** handles forcing configuration logic separately from case setup
- The **`extract_forcings` module** handles the computationally heavy work of processing data
- The **`raw_data_access` module** handles data retrieval, insulating you from the differences between data sources

This organization means:
- We can test or debug individual pieces without understanding the whole system
- Adding new functionality (like a new forcing type or data source) doesn't require modifying existing code
- The learning curve is gentler because you can focus on the piece relevant to what you're doing right now

## Extending CrocoDash

One benefit of this architecture is that CrocoDash is designed to be extended. You can:

- **Add new forcing configurations** by creating a new configuration class and registering it (see [Forcing Configurations](forcing_configurations.md))
- **Add new data sources** by implementing a new data product class in the registry (see [Adding Data Access](../for_developers/adding_data_access.md))
- **Customize bathymetry** using the interactive TopoEditor
- **Create custom configurations** by modifying JSON files or Python configuration objects

None of these require modifying CrocoDash's core code—the architecture is designed to support this kind of extension.

## What Happens When You Run Your Case

When you execute the workflow, here's what's actually happening behind the scenes:

1. **Grid Definition** - You create Python objects representing your spatial domain
2. **Case Creation** - CrocoDash calls CESM's case creation utilities to set up the directory structure
3. **Forcing Configuration** - Your specifications are validated and stored in JSON
4. **Data Processing** - CrocoDash queries remote datasets, downloads what's needed, regrids to your grid, and formats for MOM6
5. **Building** - CESM builds the executable with your specific configuration
6. **Submission** - The case runs on the supercomputer

You don't need to understand all these details to use CrocoDash, but they're here when you need them.

