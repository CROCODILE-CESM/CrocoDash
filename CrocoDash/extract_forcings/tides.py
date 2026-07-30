import pandas as pd
import xarray as xr
from regional_mom6.regional_mom6 import prepare_tpxo_tidal_forcing
from CrocoDash.extract_forcings.obc import boundary_key, get_segment


def process_tides(
    ocn_topo,
    inputdir,
    supergrid_path,
    vgrid_path,
    tidal_constituents,
    boundaries,
    tpxo_elevation_filepath,
    tpxo_velocity_filepath,
    custom_segments=None,
):
    """Regrid tidal forcing onto each boundary, driving
    regional_mom6.segment.Segment directly (Segment.cardinal / from_hgrid) --
    no regional_mom6.experiment involved. TPXO loading/preprocessing is shared
    with experiment.setup_boundary_tides via prepare_tpxo_tidal_forcing.

    ``boundaries`` are plain boundary-key strings (cardinal or custom) read
    back from config.json; ``custom_segments`` is the matching
    ``general.custom_segments`` dict (key -> ``Segment.to_spec()``), needed
    to rebuild any non-cardinal boundary via ``get_segment``.
    """
    date_range = pd.to_datetime(["1850-01-01 00:00:00", "1851-01-01 00:00:00"])
    hgrid = xr.open_dataset(supergrid_path)

    tpxo_h, tpxo_u, tpxo_v = prepare_tpxo_tidal_forcing(
        tpxo_elevation_filepath, tpxo_velocity_filepath, tidal_constituents
    )

    for idx, boundary in enumerate(boundaries):
        seg_ix = str(idx + 1).zfill(3)
        print(f"Processing {boundary_key(boundary)} boundary tides...", end="")
        segment = get_segment(
            hgrid,
            boundary,
            segment_name=f"segment_{seg_ix}",
            topo=ocn_topo,
            custom_segments=custom_segments,
        )
        segment.regrid_tides(
            tpxo_v,
            tpxo_u,
            tpxo_h,
            None,
            outfolder=inputdir / "ocnice",
            startdate=date_range[0],
            repeat_year_forcing=False,
        )
        print("Done")
