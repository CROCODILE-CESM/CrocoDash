import pytest
import numpy as np
import pandas as pd
import xarray as xr

from CrocoDash.extract_forcings import mom6
from CrocoDash.extract_forcings.mom6 import _split_bgc_tracers_into_files
from CrocoDash.forcing_configurations.configurations import ConditionsConfigurator


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
    return ConditionsConfigurator(
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


def test_split_bgc_tracers_resume_rejects_truncated_per_tracer_file(tmp_path):
    """A per-tracer file left truncated by an interrupted run is a hard error,
    not a resume-skip.

    Step 3 strips the BGC tracers out of the per-boundary files, and the
    upstream MERGE phase skips on its own output, so a silent skip here would
    hand MOM6 the truncated file with nothing left to regenerate it from.
    """
    conversion = {"south": 1}
    tracers = {"o2": "o2", "no3": "no3"}
    _write_segment_file(tmp_path / "forcing_obc_segment_001.nc", "001", tracers.keys())

    # A completed run's output, plus one file the kill caught mid-write.
    _split_bgc_tracers_into_files(tmp_path, conversion, tracers)
    (tmp_path / "no3_obc_segment.nc").write_bytes(b"truncated")

    with pytest.raises(RuntimeError, match="not valid NetCDF"):
        _split_bgc_tracers_into_files(tmp_path, conversion, tracers)


# ---------------------------------------------------------------------------
# Entry points: what MOM6 hands to the model-agnostic engines
# ---------------------------------------------------------------------------

PRODUCT_INFO = {
    "u_var_name": "uo",
    "v_var_name": "vo",
    "eta_var_name": "zos",
    "tracer_var_names": {"temp": "thetao", "salt": "so"},
    "dataset_path": "/some/path",
}
VARS = ["uo", "vo", "zos", "thetao", "so"]


def _recorder(recorded):
    def _engine(**kwargs):
        recorded.update(kwargs)
        return "engine-result"

    return _engine


def test_process_mom6_obc_wires_mom6_pieces_into_the_engine(tmp_path, monkeypatch):
    """obc.py knows nothing about MOM6: the Segment regrid step, the download
    request built from the product's var names, and the BGC split (which runs
    after the merge, on its output) all have to come from here."""
    recorded, split = {}, []
    monkeypatch.setattr(mom6.obc, "process_obc_conditions", _recorder(recorded))
    monkeypatch.setattr(
        mom6, "_split_bgc_tracers_into_files", lambda **kw: split.append(kw)
    )
    kwargs = dict(
        start_date="2020-01-01",
        end_date="2020-01-15",
        boundary_number_conversion={"east": 1},
        product_name="glorys",
        function_name="get_glorys_data_from_rda",
        product_info=dict(PRODUCT_INFO),
        hgrid_path=str(tmp_path / "hgrid.nc"),
        raw_dataset_path=str(tmp_path),
        regridded_dataset_path=str(tmp_path),
        output_path=str(tmp_path),
        bathymetry_path=str(tmp_path / "topo.nc"),
    )

    assert mom6.process_mom6_obc(**kwargs) == "engine-result"
    assert recorded["regrid_chunk_fn"] is mom6._regrid_obc_chunk
    assert recorded["variables"] == VARS
    assert recorded["extra_args"] == {"dataset_path": "/some/path"}
    assert recorded["bathymetry_path"] == kwargs["bathymetry_path"]
    assert split == [
        {
            "output_path": str(tmp_path),
            "boundary_number_conversion": {"east": 1},
            "marbl_var_names": {},
        }
    ]

    # preview only reports filenames: no request to build, nothing merged to split.
    recorded.clear()
    split.clear()
    mom6.process_mom6_obc(**kwargs, preview=True)
    assert (recorded["preview"], recorded["variables"], split) == (True, None, [])

    # _regrid_obc_chunk hardwires regional_mom6's fill; anything else must fail
    # up front rather than be silently ignored.
    kwargs["product_info"]["boundary_fill_method"] = "something_else"
    with pytest.raises(ValueError, match="is not supported"):
        mom6.process_mom6_obc(**kwargs)


def test_process_mom6_ic_binds_grid_paths_onto_the_regrid_step(tmp_path, monkeypatch):
    """ic.py's engine signature has no hgrid/vgrid/bathymetry -- MOM6 binds its
    own onto _regrid_ic with partial before handing it over."""
    recorded = {}
    monkeypatch.setattr(mom6.ic_mod, "process_initial_condition", _recorder(recorded))
    (tmp_path / "vgrid.nc").touch()
    kwargs = dict(
        product_name="glorys",
        function_name="get_glorys_data_from_rda",
        product_information=dict(PRODUCT_INFO),
        start_date="2020-01-01",
        hgrid_path=str(tmp_path / "hgrid.nc"),
        vgrid_path=str(tmp_path / "vgrid.nc"),
        dataset_varnames={},
        raw_data_dir=str(tmp_path),
        output_data_dir=str(tmp_path),
        bathymetry_path=str(tmp_path / "topo.nc"),
    )

    assert mom6.process_mom6_ic(**kwargs) == "engine-result"
    assert recorded["regrid_fn"].func is mom6._regrid_ic
    assert recorded["regrid_fn"].keywords == {
        k: kwargs[k] for k in ("hgrid_path", "vgrid_path", "bathymetry_path")
    }
    assert recorded["variables"] == VARS

    mom6.process_mom6_ic(**kwargs, preview=True)
    assert (recorded["preview"], recorded["variables"]) == (True, None)

    # _regrid_ic reads dz off the vgrid; a missing one otherwise fails deep
    # inside regional_mom6.
    kwargs["vgrid_path"] = str(tmp_path / "gone.nc")
    with pytest.raises(FileNotFoundError, match="Vgrid file must exist"):
        mom6.process_mom6_ic(**kwargs)


def test_fill_missing_and_write_leaves_no_gaps_for_mom6_to_read(tmp_path):
    """Holes inside the ocean mask are objectively interpolated, land (left at
    0.0 by mom6_forge's fill) is interpolated away, and levels below the source
    data are carried down -- nothing NaN reaches the file MOM6 reads. 3D goes
    level by level because that fill is a 2D solve, with depth as axis 0.
    """
    mask = xr.DataArray(np.ones((4, 5)), dims=("ny", "nx"))
    mask[0, :] = 0  # a row of land
    eta = np.full((4, 5), 5.0)
    eta[0, :], eta[2, 2] = np.nan, np.nan  # land, then a hole in the ocean
    temp = np.full((3, 4, 5), 8.0)
    temp[2], temp[1, 2, 2] = np.nan, np.nan  # a level below the data, then a hole
    xr.Dataset(
        {"eta_t": (("ny", "nx"), eta), "temp": (("zl", "ny", "nx"), temp)},
        coords={"zl": np.arange(3.0)},
    ).to_netcdf(tmp_path / "init.nc")

    mom6._fill_missing_and_write(
        tmp_path / "init.nc",
        tmp_path / "filled.nc",
        [
            {"name": name, "mask": mask, "dims": dims, "encoding": encoding}
            for name, dims, encoding in [
                ("eta_t", ("nx", "ny"), {"_FillValue": None}),
                ("temp", ("nx", "ny", "zl"), {"_FillValue": -1e20}),
            ]
        ],
    )

    with xr.open_dataset(tmp_path / "filled.nc") as filled:
        assert not np.isnan(filled["eta_t"].values).any()
        assert not np.isnan(filled["temp"].values).any()
        assert filled["eta_t"].values[2, 2] == pytest.approx(5.0)
        assert filled["temp"].values[1, 2, 2] == pytest.approx(8.0)
        assert filled["temp"].values[2, 1, 1] == pytest.approx(8.0)
        assert "_FillValue" not in filled["eta_t"].encoding
