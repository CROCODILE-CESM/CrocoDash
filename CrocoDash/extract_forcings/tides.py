import regional_mom6 as rmom6
from CrocoDash.grid import Grid
from CrocoDash.vgrid import VGrid


def process_tides(
    ocn_topo,
    inputdir,
    supergrid_path,
    vgrid_path,
    tidal_constituents,
    boundaries,
    tpxo_elevation_filepath,
    tpxo_velocity_filepath,
):
    # hgrid_type/vgrid_type take mom6_forge Grid/VGrid objects directly now --
    # "from_file" + a separate hgrid_path/vgrid_path kwarg no longer exists;
    # "from_file" instead means "lazily read mom_input_dir/hgrid.nc", which
    # isn't this experiment's own supergrid filename.
    expt = rmom6.experiment(
        date_range=("1850-01-01 00:00:00", "1851-01-01 00:00:00"),  # Dummy times
        resolution=None,
        number_vertical_layers=None,
        layer_thickness_ratio=None,
        depth=ocn_topo.max_depth,
        mom_run_dir=inputdir,
        mom_input_dir=inputdir / "ocnice",
        hgrid_type=Grid.from_supergrid(supergrid_path),
        vgrid_type=VGrid.from_file(str(vgrid_path)),
        minimum_depth=ocn_topo.min_depth,
        tidal_constituents=tidal_constituents,
        expt_name="tides",
        boundaries=boundaries,
    )
    expt.setup_boundary_tides(
        tpxo_elevation_filepath=tpxo_elevation_filepath,
        tpxo_velocity_filepath=tpxo_velocity_filepath,
        tidal_constituents=tidal_constituents,
    )
