# Adding Data to the Data Access Module

The Data Access Module provides access functions to raw datasets used in CrocoDash. This document explains how to add a new dataset to the module.

## Module Overview

The data access module is located in `CrocoDash/raw_data_access/` and consists of:

- **`base.py`** - `ForcingProduct` and `BaseProduct` base classes that all data sources inherit from
- **`registry.py`** - Central registry for data products and access functions
- **`datasets/`** - Individual dataset implementations (one file per product)
- **`utils.py`** - Utility functions for data handling

## Adding a New Dataset

### Step 1: Create a New Dataset File

Create a new Python file in `CrocoDash/raw_data_access/datasets/` named after your data product. See other data products for standards

```python
# CrocoDash/raw_data_access/datasets/my_dataset.py

from pathlib import Path
from typing import Tuple, Optional
import xarray as xr
from CrocoDash.raw_data_access.base import ForcingProduct # Could be not a forcing product to.
import requests

class MyDataset(ForcingProduct):
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

    required_args = BaseProduct.required_args + [
        "variables",
        "lon_max",
        "lat_max",
        "lon_min",
        "lat_min",
    ]
```

### Step 3: Register the Dataset

You register the dataset by adding the accessmethod wrapper to your access function and inheriting from the base products, like ForcingProduct. This makes it a class method as well.

```python
@accessmethod(
        description="Gathers your data from what",
        type="what type, python, script, etc...",
    )
```

## Step 4: Set required metadata.

Each class has a certain amount of metadata that is required. Classes inherited from BaseProduct pretty much just need a name. Classes inherited from ForcingProduct require quite a bit of information, which can be seen in a file like GLORYS. You can see what is required by looking at the base.py file. Here is an example in ForcingProduct: 

```python
class ForcingProduct(DatedBaseProduct):
    """Specific enforcement needs for Forcing Products"""

    required_metadata = DatedBaseProduct.required_metadata + [
        "time_var_name",
        "u_x_coord",
        "u_y_coord",
        "v_x_coord",
        "v_y_coord",
        "tracer_x_coord",
        "tracer_y_coord",
        "depth_coord",
        "u_var_name",
        "v_var_name",
        "eta_var_name",
        "tracer_var_names",
        "boundary_fill_method",
        "time_units",
    ]

```

## Step 5: Validation and Tests

When you test your class, it will automatically get registed with the registry and run validation. It will fail on import if you miss metadata or required args in your registed access function.

Create a test file in `CrocoDash/tests/raw_data_access` to test your dataset:

```python
# CrocoDash/tests/raw_data_access/test_my_dataset.py

import pytest
from pathlib import Path
from CrocoDash.raw_data_access.datasets.my_dataset import MyDataset
import xarray as xr


def test_get_data_basic(my_dataset):
    """Test basic data retrieval."""

```

Run your tests:

```bash
pytest tests/test_my_dataset.py -v
```

## ForcingProduct Base Class

The dataset classes for OBC and IC generation should inherit from `ForcingProduct`. Other things like tides or chlorophyll may only inherit from DatedBaseProduct or BaseProduct.

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
