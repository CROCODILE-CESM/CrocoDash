from unittest.mock import patch

from CrocoDash.forcing.base import WorkflowContext
from CrocoDash.forcing.runoff import RunoffConfigurator


def _make_configurator(tmp_path, rmax=20, fold=40):
    return RunoffConfigurator(
        case_grid_name="test",
        case_session_id="abc123",
        case_compset_lname="DROF",
        case_inputdir=tmp_path,
        case_is_non_local=False,
        case_esmf_mesh_path="/fake/ocn_mesh.nc",
        rmax=rmax,
        fold=fold,
        rof_grid_name="GLOFAS",
        rof_esmf_mesh_filepath="/fake/rof_mesh.nc",
    )


def _make_ctx(tmp_path):
    return WorkflowContext(
        inputdir=tmp_path,
        supergrid_path=tmp_path / "grid.nc",
        vgrid_path=tmp_path / "vgrid.nc",
        topo_path=tmp_path / "topo.nc",
        raw_data_dir=tmp_path,
        regridded_data_dir=tmp_path,
        output_path=tmp_path,
        config={},
    )


@patch("CrocoDash.forcing.runoff.mapping.gen_rof_maps", autospec=True)
def test_runoff_process(mock_gen_maps, tmp_path):
    configurator = _make_configurator(tmp_path)
    configurator.process(_make_ctx(tmp_path))

    assert mock_gen_maps.called


@patch("CrocoDash.forcing.runoff.mapping.gen_rof_maps", autospec=True)
@patch("CrocoDash.forcing.runoff.mapping.get_smoothed_map_filepath")
def test_runoff_process_reuses_existing(mock_get_filepath, mock_gen_maps, tmp_path):
    """If the smoothed-map file already exists, gen_rof_maps must not be called."""
    existing = tmp_path / "mapping" / "EXISTING_map.nc"
    existing.parent.mkdir(parents=True, exist_ok=False)
    existing.write_text("x")
    mock_get_filepath.return_value = existing

    configurator = _make_configurator(tmp_path)
    configurator.process(_make_ctx(tmp_path))

    mock_gen_maps.assert_not_called()
