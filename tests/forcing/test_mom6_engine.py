import pytest
import numpy as np
import pandas as pd
import xarray as xr

from CrocoDash.forcing import mom6


def test_build_forcing_request_merges_function_args():
    product_info = {
        "u_var_name": "uo",
        "v_var_name": "vo",
        "eta_var_name": "zos",
        "tracer_var_names": {"temp": "thetao", "salt": "so"},
        "dataset_path": "/some/path",
    }

    variables, extra_args = mom6.build_forcing_request(
        product_info, function_args={"member": 5}
    )

    assert extra_args["dataset_path"] == "/some/path"
    assert extra_args["member"] == 5


# =============================================================================
# ConditionsConfigurator.validate_args
# =============================================================================


def _conditions(product_name):
    return mom6.ConditionsConfigurator(
        boundaries=["north"],
        product_name=product_name,
        function_name="get_glorys_data_script_for_cli",
        compset="1850_DATM%JRA_SLND_SICE_MOM6%REGIONAL_SROF_SGLC_SWAV",
        start_date="20200101",
        end_date="20200102",
    )


def test_conditions_configurator_rejects_non_mom6_product():
    # A registered product of the wrong flavor (GLOFAS river discharge) and an
    # entirely unknown name are both rejected, with distinct messages.
    with pytest.raises(ValueError, match="not a MOM6ForcingProduct"):
        _conditions("glofas")

    with pytest.raises(ValueError, match="Unknown forcing product"):
        _conditions("not_a_real_product")


def test_conditions_configurator_accepts_mom6_products():
    # Doesn't raise -- GLORYS plus the CESM POP/MOM output readers all feed the
    # MOM6 IC/OBC pipeline.
    _conditions("glorys")
    _conditions("cesm_pop_output")
    _conditions("cesm_mom_output")


# ---------------------------------------------------------------------------
# BGC tracer splitting
# ---------------------------------------------------------------------------


def _write_segment_file(path, seg, tracers, nt=3, nz=4, nx=5):
    """A stand-in for a merged forcing_obc_segment_NNN.nc holding physical +
    BGC tracers, in the ``<var>_segment_NNN`` / ``dz_<var>_segment_NNN`` layout
    the regrid step produces."""
    ds = xr.Dataset()
    dims = ("time", f"nz_segment_{seg}", f"nx_segment_{seg}")
    for var in ("temp", "salt", *tracers):
        name = f"{var}_segment_{seg}"
        ds[name] = (dims, np.full((nt, nz, nx), float(len(var))))
        ds[f"dz_{name}"] = (dims, np.ones((nt, nz, nx)))
    ds["time"] = ("time", pd.date_range("2020-01-01", periods=nt))
    ds.to_netcdf(path)


def test_split_bgc_tracers_writes_one_file_per_tracer_with_all_segments(tmp_path):
    """Each BGC tracer gets its own file holding every segment.

    MOM6's generic tracer code reads BGC boundary data per tracer, not per
    segment, so OBC_DATA_<tracer> points at <tracer>_obc_segment.nc. Without
    this split those files never exist.
    """
    conversion = {"south": 1, "north": 2, "west": 3, "east": 4}
    tracers = {"o2": "o2", "no3": "no3"}
    for seg in ("001", "002", "003", "004"):
        _write_segment_file(
            tmp_path / f"forcing_obc_segment_{seg}.nc", seg, tracers.keys()
        )

    written = _split_bgc_tracers_into_files(tmp_path, conversion, tracers)

    assert sorted(p.name for p in written) == [
        "no3_obc_segment.nc",
        "o2_obc_segment.nc",
    ]
    for var in tracers:
        with xr.open_dataset(tmp_path / f"{var}_obc_segment.nc") as ds:
            for seg in ("001", "002", "003", "004"):
                assert f"{var}_segment_{seg}" in ds
                assert f"dz_{var}_segment_{seg}" in ds
            # Physical tracers stay in the per-boundary files, not here.
            assert not [v for v in ds.data_vars if v.startswith(("temp", "salt"))]

    # The per-boundary files are left intact for the physical tracers.
    for seg in ("001", "002", "003", "004"):
        with xr.open_dataset(tmp_path / f"forcing_obc_segment_{seg}.nc") as ds:
            assert f"temp_segment_{seg}" in ds


def test_split_bgc_tracers_is_a_noop_without_marbl_tracers(tmp_path):
    """Non-BGC cases must not gain any per-tracer files."""
    conversion = {"south": 1}
    _write_segment_file(tmp_path / "forcing_obc_segment_001.nc", "001", [])

    assert _split_bgc_tracers_into_files(tmp_path, conversion, {}) == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ["forcing_obc_segment_001.nc"]


def test_split_bgc_tracers_raises_when_tracer_missing_from_segment(tmp_path):
    """A tracer requested but absent from a segment file is a hard error, not a
    silently truncated output file."""
    conversion = {"south": 1}
    _write_segment_file(tmp_path / "forcing_obc_segment_001.nc", "001", ["o2"])

    with pytest.raises(KeyError, match="alk_segment_001"):
        _split_bgc_tracers_into_files(tmp_path, conversion, {"alk": "alk"})
