import numpy as np
import pandas as pd
import xarray as xr
from regional_mom6.regional_mom6 import convert_to_tpxo_tidal_constituents
from CrocoDash.extract_forcings.segment_spec import boundary_key, build_segment


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
    """Regrid tidal forcing onto each boundary, driving
    regional_mom6.segment.Segment directly (Segment.cardinal / from_hgrid) --
    no regional_mom6.experiment involved.
    """
    date_range = pd.to_datetime(["1850-01-01 00:00:00", "1851-01-01 00:00:00"])
    hgrid = xr.open_dataset(supergrid_path)

    tpxo_h = (
        xr.open_dataset(tpxo_elevation_filepath)
        .rename({"lon_z": "lon", "lat_z": "lat", "nc": "constituent"})
        .isel(constituent=convert_to_tpxo_tidal_constituents(tidal_constituents))
    )
    h = tpxo_h["ha"] * np.exp(-1j * np.radians(tpxo_h["hp"]))
    tpxo_h["hRe"] = np.real(h)
    tpxo_h["hIm"] = np.imag(h)

    tpxo_u = (
        xr.open_dataset(tpxo_velocity_filepath)
        .rename({"lon_u": "lon", "lat_u": "lat", "nc": "constituent"})
        .isel(constituent=convert_to_tpxo_tidal_constituents(tidal_constituents))
    )
    tpxo_u["ua"] *= 0.01  # convert to m/s
    u = tpxo_u["ua"] * np.exp(-1j * np.radians(tpxo_u["up"]))
    tpxo_u["uRe"] = np.real(u)
    tpxo_u["uIm"] = np.imag(u)

    tpxo_v = (
        xr.open_dataset(tpxo_velocity_filepath)
        .rename({"lon_v": "lon", "lat_v": "lat", "nc": "constituent"})
        .isel(constituent=convert_to_tpxo_tidal_constituents(tidal_constituents))
    )
    tpxo_v["va"] *= 0.01  # convert to m/s
    v = tpxo_v["va"] * np.exp(-1j * np.radians(tpxo_v["vp"]))
    tpxo_v["vRe"] = np.real(v)
    tpxo_v["vIm"] = np.imag(v)

    for idx, boundary in enumerate(boundaries):
        seg_ix = str(idx + 1).zfill(3)
        print(f"Processing {boundary_key(boundary)} boundary tides...", end="")
        segment = build_segment(
            hgrid, boundary, segment_name=f"segment_{seg_ix}", topo=ocn_topo
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
