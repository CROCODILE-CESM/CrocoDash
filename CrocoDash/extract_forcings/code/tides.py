def process_tides(
    ocn_topo,
    rundir,
    inputdir,
    supergrid_path,
    vgrid_path,
    tidal_constituents,
    boundaries,
    tpxo_elevation_filepath,
    tpxo_velocity_filepath,
):
    expt = rmom6.experiment(
        date_range=("1850-01-01 00:00:00", "1851-01-01 00:00:00"),  # Dummy times
        resolution=None,
        number_vertical_layers=None,
        layer_thickness_ratio=None,
        depth=ocn_topo.max_depth,
        mom_run_dir=rundir,
        mom_input_dir=inputdir / "ocnice",
        hgrid_type="from_file",
        hgrid_path=supergrid_path,
        vgrid_type="from_file",
        vgrid_path=vgrid_path,
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
