from mom6_forge import chl

from CrocoDash.raw_data_access.base import Calendar, NOLEAP


def process_chl(
    ocn_grid,
    ocn_topo,
    inputdir,
    chl_processed_filepath,
    output_filepath,
    calendar: Calendar = NOLEAP,
):
    chl.interpolate_and_fill_seawifs(
        ocn_grid,
        ocn_topo,
        chl_processed_filepath,
        inputdir / "ocnice" / output_filepath,
        # mom6_forge stamps this straight onto the output time coordinate,
        # which MOM6/FMS then reads, so it needs the mom6 spelling.
        calendar=calendar.mom6,
    )
