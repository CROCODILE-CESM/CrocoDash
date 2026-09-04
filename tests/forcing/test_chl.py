from unittest.mock import patch

from CrocoDash.forcing.base import WorkflowContext
from CrocoDash.forcing.chl import ChlConfigurator
from CrocoDash.raw_data_access.base import NOLEAP


@patch("CrocoDash.forcing.chl.m6f_chl.interpolate_and_fill_seawifs", autospec=True)
def test_chl_process(mock_chl, tmp_path, gen_grid_topo_vgrid):
    grid, topo, vgrid = gen_grid_topo_vgrid
    chl_path = tmp_path / "chl_source.nc"
    chl_path.touch()

    configurator = ChlConfigurator(
        chl_processed_filepath=chl_path,
        case_grid_name="test",
        case_session_id="abc123",
        calendar=NOLEAP,
    )
    # Set just the output param process() needs, bypassing configure()'s
    # super().configure() (which append_user_nl's into a real case dir).
    configurator.set_output_param("CHL_FILE", "chl.nc")

    ctx = WorkflowContext(
        inputdir=tmp_path,
        supergrid_path=tmp_path / "grid.nc",
        vgrid_path=tmp_path / "vgrid.nc",
        topo_path=tmp_path / "topo.nc",
        raw_data_dir=tmp_path,
        regridded_data_dir=tmp_path,
        output_path=tmp_path,
        config={},
    )
    ctx.grid = grid
    ctx.ocn_topo = topo

    configurator.process(ctx)

    assert mock_chl.called
