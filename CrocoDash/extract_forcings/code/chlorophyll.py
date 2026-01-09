from mom6_bathy import chl


def process_chl(ocn_grid, ocn_topo, inputdir, chl_processed_filepath, output_filepath):
    chl.interpolate_and_fill_seawifs(
        ocn_grid,
        ocn_topo,
        chl_processed_filepath,
        inputdir/"ocnice"/output_filepath,
    )
