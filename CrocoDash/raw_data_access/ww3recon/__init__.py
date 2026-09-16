"""
Vendored subset of `ww3recon` -- reconstruction of 2D wave spectra E(f, theta)
from WAVEWATCH-III partition output.

Provenance
----------
Author: Momme C. Hell (WHOI), version 0.2.0, received 2026-09-16.
Upstream is not on PyPI; the distribution is "drop the directory on your
PYTHONPATH", so it is vendored here rather than declared as a dependency.

Only the reconstruction core is vendored: `core.py` and `families.py`, with no
CrocoDash edits beyond running `black` over them, which CI checks and which
there is no way to exempt them from without adding a pyproject.toml to what is
still a setup.py project. Black is deterministic, so re-vendoring an upstream
fix stays a copy plus `dev_tools/black_CrocoDash.sh` rather than a merge
against our own reformatting. Everything else in the upstream package is
deliberately left out because CrocoDash already covers it or does not need it:

    io_iowaga.py   loads IOWAGA point/gridded files -- datasets/iowaga.py has
                   its own loader, which fetches from the file server rather
                   than the station output
    tail.py        extends the spectrum past 0.95 Hz to 20 Hz for Stokes
                   drift and mean-square slope; WW3 boundary forcing wants the
                   native band, and ww3_bounc would discard the extension
    partition.py   watershed re-partitioning of truth spectra, validation only
    validate.py    skill scoring and the direction/spread convention checkers
    selftest.py    synthetic self-test
    report.py      figures and tables
    animate.py     animations

Keeping the two files unmodified means upstream fixes drop in with a copy.
If you need the validation halves, work against the full package in
`dev/iowaga/ww3recon/` -- do not partially re-vendor them here.

Upstream's own caveats that still apply to this subset:

  * `t0m1` is REQUIRED. It is the constraint the peakedness fit is solved
    against; without it there is nothing to fit and `reconstruct` raises.
  * `t02` is optional and drives the second-stage tail-exponent fit. Without
    it the tail exponent stays at the family default.
  * The defaults (Elfouhaily wind sea, Ochi-Hubble swell) were selected on
    four IOWAGA sites for January 1993, not on a global sweep.
  * Direction convention is carried for bookkeeping only; `SpectralGrid` does
    not reinterpret angles. `_assemble` centres each lobe on `pdir` as given,
    so from-directions in means from-directions out -- which is what
    datasets/iowaga.py establishes and what forcing/ww3.py expects.
"""

from .core import (
    PartitionSet,
    ReconstructionConfig,
    Reconstructor,
    ShapeTables,
    SpectralGrid,
    bulk_parameters,
    moments,
)
from .families import FAMILIES, get_family

__all__ = [
    "PartitionSet",
    "ReconstructionConfig",
    "Reconstructor",
    "ShapeTables",
    "SpectralGrid",
    "bulk_parameters",
    "moments",
    "FAMILIES",
    "get_family",
]
__version__ = "0.2.0"
