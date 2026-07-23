def process_cice_ic(
    ocn_grid,
    inputdir,
    date_range,
    cice_product_name=None,
    cice_function_name=None,
):
    """
    Generate CICE initial conditions into <inputdir>/ocnice.

    Not implemented yet: CICE IC sourcing (e.g. GLORYS sea-ice fields, or a
    parent CESM/CICE run's own output) isn't wired through raw_data_access
    yet, so this always raises until that work lands.
    """
    raise NotImplementedError(
        "CICE initial condition generation is not implemented yet."
    )


def process_cice_obc(
    ocn_grid,
    inputdir,
    boundaries,
    date_range,
    cice_product_name=None,
    cice_function_name=None,
):
    """
    Generate CICE open boundary conditions into <inputdir>/ocnice.

    Not implemented yet: CICE OBC sourcing (e.g. GLORYS sea-ice fields, or a
    parent CESM/CICE run's own output) isn't wired through raw_data_access
    yet, so this always raises until that work lands.
    """
    raise NotImplementedError(
        "CICE boundary condition generation is not implemented yet."
    )
