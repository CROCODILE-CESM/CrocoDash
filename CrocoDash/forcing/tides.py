from datetime import datetime
from pathlib import Path

import xarray as xr
from regional_mom6.regional_mom6 import prepare_tpxo_tidal_forcing
from CrocoDash.forcing import obc
from CrocoDash.forcing.base import *


@register
class TidesConfigurator(BaseConfigurator):
    name = "tides"
    process_components = {"tides": "process"}
    input_params = [
        InputFileParam(
            "tpxo_elevation_filepath",
            comment="NetCDF file containing tidal elevation data",
        ),
        InputFileParam(
            "tpxo_velocity_filepath",
            comment="NetCDF file containing tidal velocity data",
        ),
        InputValueParam(
            "tidal_constituents",
            comment="List of tidal constituents to include",
        ),
        InputValueParam(
            "start_date",
            comment="start_date",
        ),
        InputValueParam(
            "boundaries",
            comment="boundaries to apply tidal forcing (e.g., ['N', 'S', 'E', 'W'])",
        ),
    ]
    output_params = [
        UserNLConfigParam("TIDES", comment="Enable tidal forcing in MOM6"),
        UserNLConfigParam("TIDE_M2", comment="Enable M2 tidal constituent"),
        UserNLConfigParam("CD_TIDES", comment="Drag coefficient for tidal forcing"),
        UserNLConfigParam(
            "TIDE_USE_EQ_PHASE", comment="Use equilibrium phase for tides"
        ),
        UserNLConfigParam("TIDE_REF_DATE", comment="Reference date for tidal forcing"),
        UserNLConfigParam(
            "OBC_TIDE_ADD_EQ_PHASE", comment="Add equilibrium phase to OBC tides"
        ),
        UserNLConfigParam(
            "OBC_TIDE_N_CONSTITUENTS", comment="Number of tidal constituents"
        ),
        UserNLConfigParam(
            "OBC_TIDE_CONSTITUENTS", comment="List of tidal constituents"
        ),
        UserNLConfigParam(
            "OBC_TIDE_REF_DATE", comment="Reference date for OBC tidal forcing"
        ),
    ]

    def __init__(
        self,
        tpxo_elevation_filepath,
        tpxo_velocity_filepath,
        tidal_constituents,
        boundaries,
        date_range=None,
        start_date=None,
    ):
        if date_range is not None:
            # Set the input params
            super().__init__(
                tpxo_elevation_filepath=tpxo_elevation_filepath,
                tpxo_velocity_filepath=tpxo_velocity_filepath,
                tidal_constituents=tidal_constituents,
                start_date=date_range[0].strftime("%Y, %m, %d"),
                boundaries=boundaries,
            )
        else:
            super().__init__(
                tpxo_elevation_filepath=tpxo_elevation_filepath,
                tpxo_velocity_filepath=tpxo_velocity_filepath,
                tidal_constituents=tidal_constituents,
                start_date=start_date,
                boundaries=boundaries,
            )

    def configure(self):
        # Set the output params
        self.set_output_param("TIDES", "True")
        self.set_output_param("TIDE_M2", "True")
        self.set_output_param("CD_TIDES", 0.0018)
        self.set_output_param("TIDE_USE_EQ_PHASE", "True")
        self.set_output_param(
            "TIDE_REF_DATE",
            self.get_input_param("start_date"),
        )
        self.set_output_param("OBC_TIDE_ADD_EQ_PHASE", "True")
        self.set_output_param(
            "OBC_TIDE_N_CONSTITUENTS",
            len(self.get_input_param("tidal_constituents")),
        )
        self.set_output_param(
            "OBC_TIDE_CONSTITUENTS",
            '"' + ", ".join(self.get_input_param("tidal_constituents")) + '"',
        )
        self.set_output_param(
            "OBC_TIDE_REF_DATE",
            self.get_input_param("start_date"),
        )
        super().configure()
        # You also need to add the files to the OBC string, which is handled in the main case unfortunately

    def output_files(self, ctx):
        # regional_mom6 numbers segments by position in `boundaries`, the same
        # numbering the conditions OBC strings that name these files use.
        n_segments = len(self.get_input_param("boundaries"))
        return {
            "tides": [
                ctx.output_path / f"{kind}_segment_{n:03d}.nc"
                for n in range(1, n_segments + 1)
                for kind in ("tz", "tu")
            ]
        }

    def process(self, ctx):
        """Regrid TPXO onto each boundary's regional_mom6 Segment, interior
        segments included."""
        tpxo_h, tpxo_u, tpxo_v = prepare_tpxo_tidal_forcing(
            self.get_input_param("tpxo_elevation_filepath"),
            self.get_input_param("tpxo_velocity_filepath"),
            self.get_input_param("tidal_constituents"),
        )
        with xr.open_dataset(ctx.supergrid_path) as hgrid:
            for n, boundary in enumerate(self.get_input_param("boundaries"), start=1):
                segment = obc.get_segment(hgrid, boundary, f"segment_{n:03d}")
                segment.regrid_tides(
                    tpxo_v,
                    tpxo_u,
                    tpxo_h,
                    None,
                    outfolder=ctx.output_path,
                    startdate=datetime(1850, 1, 1),  # Dummy time
                )
