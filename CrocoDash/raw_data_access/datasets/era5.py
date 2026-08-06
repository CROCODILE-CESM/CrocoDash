"""
Data Access Module -> ERA5 (true 2D wave spectra)

Fetches ERA5's true 2D wave energy-density spectrum E(f, theta) -- ECMWF
parameter 251.140, "wave" stream -- via CDS's MARS-style
`reanalysis-era5-complete` access, NOT the bulk/integrated wave stats
(significant height, mean direction, mean period) available on the
friendlier `reanalysis-era5-single-levels` dataset.

Real pulls against cds.climate.copernicus.eu (2026-08-03) confirmed the
actual on-the-wire shape, which is not a plain multi-dim GRIB field:

- Requesting just `param: "251.140"` returns ONE message per timestep, all
  pinned at directionNumber=1/frequencyNumber=1 -- MARS does not expand the
  spectrum unless explicitly told to. Getting the full 2D spectrum requires
  explicit `direction`/`frequency` MARS keys (1-based bin *indices*, not
  physical values): `"direction": "1/to/24"`, `"frequency": "1/to/30"`. That
  turns one timestep into 24*30=720 separate GRIB messages (one per
  direction/frequency bin), confirmed via eccodes message iteration.
- Real direction bins (`coefsFirst` GRIB key, degrees) and frequency bins
  (`coefsSecond` GRIB key, Hz) follow ECMWF's standard WAM discretization:
  24 directions 15 degrees apart starting at 7.5 degrees, 30 frequencies
  starting at ~0.0345 Hz on a geometric ratio of 1.1 -- fixed for every
  message in a file, read once from the first message.
- Values are base-10 log-encoded (observed values like -2.98, consistent
  with ECMWF's documented convention of storing log10 of spectral density
  to compress dynamic range) with a per-message `missingValue` sentinel
  (9999.0 seen in practice) marking bins with no energy -- decoded here as
  `10**value` where present, `0.0` where missing. The vast majority of
  (direction, frequency) messages in a real pull ARE the missing sentinel
  (597 of 720 in a 1-hour Bering Sea test pull) -- only bins actually
  carrying energy get a real value.
- `cfgrib`'s default `xr.open_dataset` engine does NOT reconstruct this
  correctly: without an explicit hint that directionNumber/frequencyNumber
  vary, it silently keeps only the first (dn=1, fn=1) message per
  time/space point and drops the rest -- exactly what was observed on an
  unexpanded (single-bin) file, and would still be a silent underdecode on
  an expanded one. Because of this, decoding here bypasses cfgrib entirely
  and reads GRIB messages directly via eccodes.
- `"grid": "0.5/0.5"` in the request (added below) forces ECMWF's native
  Reduced Lat-Lon wave grid to be regridded onto a regular lat/lon grid
  server-side -- required because MARS/MIR cannot crop ("area") the native
  representation directly (raises
  ``ReducedLL::croppedRepresentation() not supported``). `"data_format"`
  replaces the deprecated `"format"` request key.

Given all of the above, `get_era5_2d_spectra` below does not hand back a
raw, unopened GRIB file the way GLORYS/GLOFAS/CICE_RESTART's accessmethods
do -- there is no generic downstream tool that decodes this file's shape
correctly, so decoding into a clean, real-dimensioned NetCDF file (time,
latitude, longitude, frequency, direction) happens here, at fetch time,
before handing off to extract_forcings/ww3.py.

One assumption is carried through UNVERIFIED by direct sanity check (no
independent physical validation was done against a known reference
spectrum, just documented ECMWF convention): direction is the "coming
from" convention, clockwise from true north -- matches what
extract_forcings/ww3.py's write_ww3_boundary_spectrum already expects/
converts internally.

Requires a cdsapi config pointed at cds.climate.copernicus.eu with
reanalysis-era5-complete access accepted on the CDS site -- NOT the
~/.cdsapirc already on this system, which points at
ewds.climate.copernicus.eu (the Early Warning Data Store used by the
existing GLOFAS product's CEMS dataset).
"""

import os
from pathlib import Path

import cdsapi
import numpy as np
import pandas as pd
import xarray as xr

from CrocoDash.raw_data_access.base import *

# cdsapi.Client() resolves its config from $CDSAPI_RC, falling back to
# ~/.cdsapirc if unset -- on this system that default points at EWDS (used
# by GLOFAS), not CDS proper. If the caller hasn't already scoped CDSAPI_RC
# themselves (e.g. per-subprocess), fall back to this ERA5-specific rc file
# instead, rather than silently hitting the wrong service (see module
# docstring). Never read/print the key itself -- only pass the path along.
_ERA5_CDSAPI_RC = Path("~/.cdsapirc_era5").expanduser()


def _era5_cdsapi_client():
    if "CDSAPI_RC" in os.environ or not _ERA5_CDSAPI_RC.exists():
        return cdsapi.Client()
    original = os.environ.get("CDSAPI_RC")
    os.environ["CDSAPI_RC"] = str(_ERA5_CDSAPI_RC)
    try:
        return cdsapi.Client()
    finally:
        if original is None:
            os.environ.pop("CDSAPI_RC", None)
        else:
            os.environ["CDSAPI_RC"] = original


def build_era5_spectra_request(
    dates: list,
    lat_min,
    lat_max,
    lon_min,
    lon_max,
    buffer_deg=1.0,
) -> dict:
    """Pure builder for a CDS `reanalysis-era5-complete` (MARS-style)
    request dict for ERA5's 2D wave spectra (param 251.140, wave stream) --
    no network I/O, so it's unit-testable without cdsapi credentials.

    `buffer_deg` pads the requested box before slicing -- needed because a
    boundary's box from mom6_forge.Grid.get_bounding_boxes is a near-zero-
    width strip (e.g. "north" spans the full domain longitude at essentially
    one latitude), and a literal zero-height CDS `area` request could miss
    every real ERA5 grid point. Same reasoning GLORYS's own accessmethods
    already use (padding lat_min-1/lat_max+1 before slicing).

    VERIFIED against real pulls (2026-08-03): the date/time/area string
    syntax below works. Three things an initial pull got wrong, now fixed:
    - Without explicit "direction"/"frequency" keys, MARS returns only a
      single (directionNumber=1, frequencyNumber=1) bin per timestep, not
      the full spectrum -- confirmed by decoding the returned GRIB directly
      via eccodes. "1/to/24"/"1/to/30" (1-based bin indices, matching this
      dataset's fixed 24-direction/30-frequency discretization) requests
      every bin, turning one timestep into 24*30 GRIB messages.
    - The wave model's native grid is a Reduced Lat-Lon grid, and MARS/MIR
      cannot crop that representation directly -- "area" alone raised
      ``ReducedLL::croppedRepresentation() not supported``. Requesting
      server-side regridding onto a regular grid via "grid" first (before
      cropping) is the standard fix and is what's below.
    - "format" is deprecated in favor of "data_format" (CDS now warns but
      still honors "format"; use the current key name).
    """
    start, end = pd.to_datetime(dates[0]), pd.to_datetime(dates[-1])
    return {
        "class": "ea",
        "expver": "1",
        "stream": "wave",
        "type": "an",
        "levtype": "sfc",
        "param": "251.140",
        "date": f"{start:%Y-%m-%d}/to/{end:%Y-%m-%d}",
        "time": "00/to/23/by/1",
        "direction": "1/to/24",
        "frequency": "1/to/30",
        "area": (
            f"{lat_max + buffer_deg}/{lon_min - buffer_deg}/"
            f"{lat_min - buffer_deg}/{lon_max + buffer_deg}"
        ),  # N/W/S/E
        "grid": "0.5/0.5",  # regrid off the native Reduced Lat-Lon grid so "area" cropping works
        "data_format": "grib",
    }


def _read_era5_grib_messages(path):
    """I/O: reads every GRIB message in `path` directly via eccodes,
    bypassing cfgrib (see module docstring for why cfgrib's default decode
    silently drops messages here). Returns raw ingredients for
    `_assemble_era5_dataset` -- kept separate so the actual decode math
    (log10 + missing-value handling) is unit-testable without a real GRIB
    file.
    """
    import eccodes

    directions = frequencies = None
    latitudes = longitudes = None
    n_lat = n_lon = None
    times = []
    raw = {}

    with open(path, "rb") as f:
        while True:
            gid = eccodes.codes_grib_new_from_file(f)
            if gid is None:
                break
            try:
                if directions is None:
                    directions = np.asarray(
                        eccodes.codes_get_array(gid, "coefsFirst"), dtype=np.float64
                    )
                    frequencies = np.asarray(
                        eccodes.codes_get_array(gid, "coefsSecond"), dtype=np.float64
                    )
                    n_lon = eccodes.codes_get(gid, "Ni")
                    n_lat = eccodes.codes_get(gid, "Nj")
                    lat0 = eccodes.codes_get(gid, "latitudeOfFirstGridPointInDegrees")
                    lat1 = eccodes.codes_get(gid, "latitudeOfLastGridPointInDegrees")
                    lon0 = eccodes.codes_get(gid, "longitudeOfFirstGridPointInDegrees")
                    lon1 = eccodes.codes_get(gid, "longitudeOfLastGridPointInDegrees")
                    latitudes = np.linspace(lat0, lat1, n_lat)
                    longitudes = np.linspace(lon0, lon1, n_lon)

                dn = eccodes.codes_get(gid, "directionNumber")
                fn = eccodes.codes_get(gid, "frequencyNumber")
                date = eccodes.codes_get(gid, "dataDate")
                time = eccodes.codes_get(gid, "dataTime")
                missing_value = eccodes.codes_get(gid, "missingValue")
                values = eccodes.codes_get_values(gid)

                key = pd.Timestamp(f"{date:08d}") + pd.Timedelta(
                    hours=time // 100, minutes=time % 100
                )
                if key not in times:
                    times.append(key)
                raw[(dn, fn, key)] = (values, missing_value)
            finally:
                eccodes.codes_release(gid)

    if directions is None:
        raise ValueError(f"No GRIB messages found in {path}.")

    return {
        "directions": directions,
        "frequencies": frequencies,
        "latitudes": latitudes,
        "longitudes": longitudes,
        "n_lat": n_lat,
        "n_lon": n_lon,
        "times": sorted(times),
        "raw": raw,
    }


def _assemble_era5_dataset(
    directions, frequencies, latitudes, longitudes, n_lat, n_lon, times, raw
):
    """Pure: builds a decoded xr.Dataset from `_read_era5_grib_messages`'s
    ingredients. No I/O -- unit-testable with fabricated `raw` entries.

    ERA5's 2D wave spectra param (251.140) stores log10(spectral density)
    per (direction, frequency, space, time) GRIB message, with a
    per-message missing-value sentinel marking bins carrying no energy
    (the vast majority, in practice -- wave energy is concentrated in a few
    bins). Decodes as `10**value` where present, `0.0` where missing.
    """
    n_time = len(times)
    n_dir = len(directions)
    n_freq = len(frequencies)
    time_index = {t: i for i, t in enumerate(times)}

    efth = np.zeros((n_time, n_lat, n_lon, n_freq, n_dir), dtype=np.float32)
    for (dn, fn, t), (values, missing_value) in raw.items():
        grid = np.asarray(values, dtype=np.float64).reshape(n_lat, n_lon)
        is_missing = grid == missing_value
        decoded = np.power(10.0, np.where(is_missing, 0.0, grid))
        decoded[is_missing] = 0.0
        efth[time_index[t], :, :, fn - 1, dn - 1] = decoded

    return xr.Dataset(
        {
            "efth": (
                ("time", "latitude", "longitude", "frequency", "direction"),
                efth,
            )
        },
        coords={
            "time": list(times),
            "latitude": latitudes,
            "longitude": longitudes,
            "frequency": ("frequency", frequencies, {"units": "s-1"}),
            "direction": (
                "direction",
                directions,
                {
                    "units": "degree",
                    "comment": "coming from, clockwise from true north",
                },
            ),
        },
    )


def decode_era5_spectra_grib(path):
    """Reads a raw ERA5 2D wave spectra GRIB file (as downloaded by
    `get_era5_2d_spectra`) into a clean xr.Dataset with real dims (time,
    latitude, longitude, frequency, direction). See module docstring for
    why this can't just be `xr.open_dataset(path, engine="cfgrib")`.
    """
    ingredients = _read_era5_grib_messages(path)
    return _assemble_era5_dataset(**ingredients)


class ERA5_WAVE_SPECTRA(WW3ForcingProduct):
    product_name = "era5_wave_spectra"
    description = (
        "ERA5's true 2D wave energy-density spectrum E(f, theta) (ECMWF "
        "param 251.140, wave stream) from Copernicus CDS's "
        "reanalysis-era5-complete dataset -- NOT the bulk/integrated wave "
        "stats (significant height, mean direction, mean period) available "
        "on reanalysis-era5-single-levels."
    )
    link = "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-complete"
    # Matches decode_era5_spectra_grib's "time" coord (real datetime64,
    # hourly -- see module docstring), confirmed against a real pull.
    time_var_name = "time"
    time_units = "hours"
    calendar = GREGORIAN

    @accessmethod(
        description=(
            "Gets ERA5's true 2D wave spectra via the cdsapi package from "
            "CDS's reanalysis-era5-complete (MARS-style) dataset, decodes "
            "the returned GRIB (see module docstring for why cfgrib can't "
            "do this directly), and writes a clean NetCDF file with real "
            "(time, latitude, longitude, frequency, direction) dims. "
            "Requires a cdsapi config pointed at cds.climate.copernicus.eu "
            "with reanalysis-era5-complete access -- NOT the ~/.cdsapirc "
            "EWDS config GLOFAS uses."
        ),
        type="python",
    )
    def get_era5_2d_spectra(
        dates: list,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
        name=None,
        output_folder=Path(""),
        output_filename="era5_spectra.nc",
        variables=None,
    ):
        """
        Downloads ERA5's true 2D wave spectra for the requested date range
        and bounding box using the cdsapi package, decodes the GRIB
        response, and writes the result as NetCDF at
        output_folder/output_filename. Note that `variables` is unused --
        param 251.140 already *is* the whole 2D spectrum -- it's kept only
        to satisfy ForcingProduct's required_args contract.

        Returns the NetCDF path, not the intermediate GRIB -- downstream
        code (extract_forcings/ww3.py) never touches GRIB/eccodes directly.
        """
        request = build_era5_spectra_request(dates, lat_min, lat_max, lon_min, lon_max)

        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)
        grib_path = output_folder / f"{Path(output_filename).stem}_raw.grib"
        nc_path = output_folder / output_filename

        client = _era5_cdsapi_client()
        client.retrieve("reanalysis-era5-complete", request, grib_path)

        ds = decode_era5_spectra_grib(grib_path)
        ds.to_netcdf(nc_path)
        ds.close()
        grib_path.unlink()
        return nc_path
