from mom6_bathy import mapping


def generate_rof_ocn_map(
    rof_grid_name,
    rof_esmf_mesh_filepath,
    ocn_mesh_filepath,
    inputdir,
    grid_name,
    rmax,
    fold,
 ):
    """Generate runoff to ocean mapping files if runoff is active in the compset."""

    assert rof_grid_name is not None, "Couldn't determine runoff grid name."
    assert rof_esmf_mesh_filepath != "", "Runoff ESMF mesh path could not be found."

    ocn_grid_name = grid_name
    mapping_file_prefix = f"{rof_grid_name}_to_{ocn_grid_name}_map"
    mapping_dir = inputdir / "mapping"
    mapping_dir.mkdir(exist_ok=False)

    runoff_mapping_file_nnsm = mapping.get_smoothed_map_filepath(
        mapping_file_prefix=mapping_file_prefix,
        output_dir=mapping_dir,
        rmax=int(rmax),
        fold=int(fold),
    )

    if not runoff_mapping_file_nnsm.exists():
        print("Creating runoff mapping file(s)...")
        print(ocn_mesh_filepath)
        mapping.gen_rof_maps(
            rof_mesh_path=rof_esmf_mesh_filepath,
            ocn_mesh_path=ocn_mesh_filepath,
            output_dir=mapping_dir,
            mapping_file_prefix=mapping_file_prefix,
            rmax=int(rmax),
            fold=int(fold),
        )
    else:
        print(
            f"Runoff mapping file {self.runoff_mapping_file_nnsm} already exists, reusing it."
        )
