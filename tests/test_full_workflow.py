"""End-to-end Case.configure_forcings()/process_forcings() across all three
engines (MOM6 + CICE + WW3) at once, driven entirely by the fast synthetic
reference_ocean/reference_ice/reference_waves products -- no network or
/glade-only real-data dependency, so this runs as a normal (non-slow,
non-glade-gated) test everywhere a real CESMROOT is available (see
CrocoDash_case_factory).
"""

import xarray as xr

_COMPSET = "2000_DATM%JRA_SLND_CICE%PRES_MOM6_SROF_SGLC_WW3"


def test_full_case_workflow_with_reference_products(CrocoDash_case_factory, tmp_path):
    case = CrocoDash_case_factory(tmp_path, compset=_COMPSET)

    case.configure_forcings(
        date_range=["2020-01-01 00:00:00", "2020-01-02 00:00:00"],
        boundaries=["north", "south"],
        product_name="reference_ocean",
        function_name="get_reference_ocean_data",
        cice_product_name="reference_ice",
        cice_function_name="get_reference_ice_data",
        ww3_obc_product_name="reference_waves",
        ww3_obc_function_name="get_reference_wave_spectra",
    )
    case.process_forcings()

    ocean_dir = case.inputdir / "ocean"
    for name in ("init_eta_filled.nc", "init_vel_filled.nc", "init_tracers_filled.nc"):
        assert (ocean_dir / name).exists()
    for seg in ("001", "002"):
        obc_file = ocean_dir / f"forcing_obc_segment_{seg}.nc"
        assert obc_file.exists()
        ds = xr.open_dataset(obc_file)
        try:
            assert "time" in ds.dims
        finally:
            ds.close()

    cice_file = case.inputdir / "sea_ice" / "cice_forcing.nc"
    assert cice_file.exists()
    ds = xr.open_dataset(cice_file)
    try:
        assert "aicen" in ds
    finally:
        ds.close()

    wave_dir = case.inputdir / "wave"
    spec_lines = (wave_dir / "spec.list").read_text().splitlines()
    assert len(spec_lines) > 0
    for line in spec_lines:
        assert (wave_dir / line).exists()
