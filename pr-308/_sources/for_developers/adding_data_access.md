# Adding Data to the Data Access Module

The Data Access Module is an expandible, verifyable, object-oriented module with access functions to raw datasets used in CrocoDash. This document explains what it is and what you can do to add more to it, if you would like to!

## Module Overview

The data access module is located in `CrocoDash/raw_data_access/` and consists of:

- **`base.py`** - the base-class hierarchy every data source inherits from, plus
  the `@accessmethod` decorator and the `Calendar` type
- **`registry.py`** - `ProductRegistry`, the central registry for data products
  and access functions
- **`datasets/`** - individual dataset implementations (one file per product),
  plus `datasets/utils.py` for shared dataset helpers

### The base-class hierarchy

Pick the most specific base that fits — each level adds required metadata:

```
BaseProduct                    product_name, description, link
 └─ DatedBaseProduct           + a `dates` download arg
     └─ ForcingProduct         + lat/lon/variables bbox contract,
                                 time_var_name, time_units, calendar
         └─ VelocityTracerForcingProduct
                               + u/v/tracer coordinate and variable names
             └─ MOM6ForcingProduct
                               + eta_var_name, boundary_fill_method
```

| Your product is… | Inherit from |
|---|---|
| An OBC/IC source for MOM6 (GLORYS, CESM output, …) | `MOM6ForcingProduct` |
| A gridded, time-varying forcing for some other model | `VelocityTracerForcingProduct` or `ForcingProduct` |
| A dated but non-gridded product (GLOFAS) | `DatedBaseProduct` |
| A static file (GEBCO, SRTM, SeaWiFS, TPXO) | `BaseProduct` |

## Adding a New Dataset

### Step 1: Create a New Dataset File

Create a new Python file in `CrocoDash/raw_data_access/datasets/` named after your data product. See other data products for standards

```python
# CrocoDash/raw_data_access/datasets/my_dataset.py

from pathlib import Path
from typing import Tuple, Optional
import xarray as xr
# `import *` brings in the base classes, `accessmethod`, and the shared
# Calendar constants (GREGORIAN, NOLEAP, ...).
from CrocoDash.raw_data_access.base import *
import requests

class MyDataset(MOM6ForcingProduct):
    """
    Access data from MyDataSource.

    This class downloads and caches data from MyDataSource for use in CrocoDash.
    """
```

### Step 2: Create your access function

You can create an access function for your data by defining a function in your class (do not add cls or self variables). In `base.py`, there is the declared class you've inherited from. In it, it has required args. Your access function must implement these required args. For example, forcing product required args are here:


```python
class ForcingProduct(DatedBaseProduct):
    """Specific enforcement needs for Forcing Products"""

    required_args = DatedBaseProduct.required_args + [
        "variables",
        "lon_max",
        "lat_max",
        "lon_min",
        "lat_min",
        "name",
    ]
```

`required_args` accumulates down the chain, so a `ForcingProduct` access
function must accept `output_folder` and `output_filename` (from `BaseProduct`)
and `dates` (from `DatedBaseProduct`) as well as the five above.

### Step 3: Register the Dataset

You register the dataset by adding the accessmethod wrapper to your access function and inheriting from the base products, like ForcingProduct. This makes it a class method as well.

```python
@accessmethod(
    description="Gathers your data from what",
    type="python",  # "python" or "script"
    how_to_use="Any setup notes shown to the user, e.g. credentials needed",
)
def get_my_data(output_folder, output_filename, dates, variables,
                lat_min, lat_max, lon_min, lon_max, name):
    ...
```

`@accessmethod` wraps the function in a `staticmethod` for you, which is why it
takes neither `self` nor `cls`. Its `description` and `type` are what appear in
the generated [Datasets](../for_users/datasets.md) table.

## Step 4: Set required metadata.

Each class has a certain amount of metadata that is required. Classes inherited from BaseProduct pretty much just need a name. Classes inherited from ForcingProduct require quite a bit of information, which can be seen in a file like GLORYS. You can see what is required by looking at the base.py file. Here is an example in ForcingProduct: 

```python
class ForcingProduct(DatedBaseProduct):
    required_metadata = DatedBaseProduct.required_metadata + [
        "time_var_name",
        "time_units",
        "calendar",
    ]


class VelocityTracerForcingProduct(ForcingProduct):
    required_metadata = ForcingProduct.required_metadata + [
        "u_x_coord", "u_y_coord",
        "v_x_coord", "v_y_coord",
        "tracer_x_coord", "tracer_y_coord",
        "u_var_name", "v_var_name",
        "tracer_var_names",
        "depth_coord",
    ]


class MOM6ForcingProduct(VelocityTracerForcingProduct):
    required_metadata = VelocityTracerForcingProduct.required_metadata + [
        "eta_var_name",
        "boundary_fill_method",
    ]
```

:::{important}
`calendar` must be a **`Calendar` instance**, not a bare string — use a
module-level constant such as `GREGORIAN` or `NOLEAP` from
`raw_data_access.base`. One `Calendar` carries the cf/cesm/mom6 names together
so they cannot disagree, and `ForcingProduct.__init_subclass__` asserts on it at
import time:

```python
class MyDataset(MOM6ForcingProduct):
    product_name = "MYDATA"
    calendar = GREGORIAN
    ...
```

`MOM6ForcingProduct` additionally asserts that `tracer_var_names` is a dict
containing at least `temp` and `salt`.
:::

## Step 5: Validation and Tests

When you test your class, it will automatically get registered with the registry and run validation. It will fail on import if you miss metadata or required args in your registered access function, or if `calendar` is missing or is not a `Calendar`.

Create a test file in `tests/raw_data_access` to test your dataset:

```python
# tests/raw_data_access/test_my_dataset.py

import pytest
from pathlib import Path
from CrocoDash.raw_data_access.datasets.my_dataset import MyDataset
import xarray as xr


def test_get_data_basic(my_dataset):
    """Test basic data retrieval."""

```

Run your tests:

```bash
pytest tests/raw_data_access/test_my_dataset.py -v
```

## Choosing a Base Class

The dataset classes that feed CrocoDash's MOM6 OBC/IC pipeline (`GLORYS`,
`CESM_POP_OUTPUT`, `CESM_MOM_OUTPUT`, `REFERENCE_OCEAN`) inherit from
`MOM6ForcingProduct`. Products that are only a static file or a non-gridded
download — tides, chlorophyll, bathymetry, runoff — inherit from
`DatedBaseProduct` or `BaseProduct` instead, and are not held to the
velocity/tracer metadata contract. See the table in **Module Overview** above.

## Error Handling Best Practices

1. **Validate inputs early:**
   ```python
   if start_date >= end_date:
       raise ValueError("Invalid date range")
   ```

2. **Handle network errors gracefully:**
   ```python
   try:
       response = requests.get(url, timeout=30)
       response.raise_for_status()
   except requests.RequestException as e:
       raise RuntimeError(f"Failed to download data: {e}")
   ```

3. **Provide informative error messages:**
   ```python
   # Bad:
   raise ValueError("Error")
   
   # Good:
   raise ValueError(f"Data not available for dates {start_date} to {end_date}")
   ```

4. **Log important events (each class comes with a logger variable):**
   ```python
   myProduct.logger.info(f"Downloading data from {url}")
   myProduct.logger.warning(f"Cache miss for {cache_file}")
   ```


## Example: Complete Implementation

See the glorys.py dataset for a complete example of adding a new dataset with:
- Dataset class implementation
- Registry updates
- Tests
- Documentation
