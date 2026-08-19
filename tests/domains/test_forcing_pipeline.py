"""End-to-end forcing generation, swept across the domain catalog.

Runs the real pipeline -- Case -> configure_forcings -> process_forcings --
against REFERENCE_OCEAN, the deterministic in-memory synthetic product. No
network, no credentials, no campaign storage, so the whole sweep runs anywhere
a CESM root is available.

Marked `workflow` because it builds real CESM cases, so it is excluded by the
suite's usual `-m "not workflow"`. Default domain selection is the `cheap`
tier; widen deliberately:

    pytest tests/domains/test_forcing_pipeline.py -m workflow --all-domains

This is the tier that catches seam and polar bugs the pure-grid tests cannot:
a bad bounding box produces a file that exists and opens cleanly but is
entirely NaN, which is why test_outputs_are_not_all_nan matters more than it
looks.
"""

import numpy as np
import pytest
import xarray as xr

from CrocoDash.extract_forcings.utils import is_valid_netcdf
from tests.fixtures.domains import configure_domain_forcings

pytestmark = [pytest.mark.workflow, pytest.mark.needs_forcing]

DATE_RANGE = ["2020-01-01 00:00:00", "2020-01-03 00:00:00"]

# What a completed run must leave in the case's input directory.
OBC_FILES = [f"forcing_obc_segment_{i:03d}.nc" for i in (1, 2, 3, 4)]
IC_FILES = ["init_tracers.nc", "init_eta.nc", "init_vel.nc"]


@pytest.fixture
def processed_case(domain_case, skip_if_not_glade):
    """A case with REFERENCE_OCEAN forcing configured and processed."""
    configure_domain_forcings(domain_case, date_range=DATE_RANGE)
    domain_case.process_forcings()
    return domain_case


def _output_files(case):
    return sorted(case.inputdir.rglob("*.nc"))


def _find(case, name):
    matches = [p for p in _output_files(case) if p.name == name]
    assert matches, (
        f"{name} was never produced. Files under {case.inputdir}: "
        f"{[p.name for p in _output_files(case)]}"
    )
    return matches[0]


def test_obc_and_ic_files_exist(processed_case):
    for name in OBC_FILES + IC_FILES:
        _find(processed_case, name)


def test_outputs_are_valid_netcdf(processed_case):
    for name in OBC_FILES + IC_FILES:
        path = _find(processed_case, name)
        assert is_valid_netcdf(path), f"{name} is not a readable netCDF"


def test_outputs_are_not_all_nan(processed_case):
    """The characteristic symptom of a seam or polar bounding-box bug.

    A domain whose source-data bbox is computed wrongly still regrids and still
    writes a well-formed file -- it just interpolates from nothing, so every
    value comes out NaN. Nothing upstream raises, which is exactly why this
    needs to be asserted rather than assumed.
    """
    for name in OBC_FILES + IC_FILES:
        path = _find(processed_case, name)
        with xr.open_dataset(path, decode_timedelta=False) as ds:
            for var, da in ds.data_vars.items():
                if not np.issubdtype(da.dtype, np.floating):
                    continue
                assert not np.isnan(da.values).all(), f"{name}:{var} is entirely NaN"
