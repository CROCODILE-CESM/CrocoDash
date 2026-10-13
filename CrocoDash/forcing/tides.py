from pathlib import Path

import pandas as pd
import xarray as xr
from regional_mom6.regional_mom6 import prepare_tpxo_tidal_forcing
from CrocoDash.forcing.obc import boundary_key, get_segment
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
        # Store boundary-key strings only -- a live Segment (custom boundary)
        # isn't JSON-serializable, and ConditionsConfigurator's config.json
        # output (conditions.outputs.custom_segments) already carries its
        # full spec for reconstruction at process() time.
        boundaries = [boundary_key(b) for b in boundaries]
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

    def get_output_filepaths(self, ocn_ice_directory):
        # Search directory for tu_* and tz_* files
        ocn_ice_directory = Path(ocn_ice_directory)

        if not ocn_ice_directory.exists():
            raise FileNotFoundError(f"{ocn_ice_directory} does not exist")

        return [
            str(p.resolve())
            for pattern in ("tu_*", "tz_*")
            for p in ocn_ice_directory.glob(pattern)
            if p.is_file()
        ]

    def process(self, ctx):
        """Regrid tidal forcing onto each boundary, driving
        regional_mom6.segment.Segment directly (Segment.cardinal/from_hgrid
        via get_segment) -- no regional_mom6.experiment involved. TPXO
        loading/preprocessing is shared with experiment.setup_boundary_tides
        via prepare_tpxo_tidal_forcing.

        custom_segments (boundary key -> Segment.to_spec()) comes from
        ConditionsConfigurator's own config.json output, not this
        configurator's -- the same physical boundaries are shared between
        MOM6's OBC and its tidal forcing, so there's only one spec to carry,
        same cross-configurator pattern BGCRiverNutrients uses for runoff's
        mapping file (see driver.py's _PROCESS_ORDER_OVERRIDES).
        """
        boundaries = self.get_input_param("boundaries")
        custom_segments = (
            ctx.config.get("conditions", {}).get("outputs", {}).get("custom_segments")
            or {}
        )
        hgrid = xr.open_dataset(ctx.supergrid_path)

        tpxo_h, tpxo_u, tpxo_v = prepare_tpxo_tidal_forcing(
            self.get_input_param("tpxo_elevation_filepath"),
            self.get_input_param("tpxo_velocity_filepath"),
            self.get_input_param("tidal_constituents"),
        )

        date_range = pd.to_datetime(
            ["1850-01-01 00:00:00", "1851-01-01 00:00:00"]
        )  # Dummy times
        for idx, boundary in enumerate(boundaries):
            seg_ix = str(idx + 1).zfill(3)
            segment = get_segment(
                hgrid,
                boundary,
                segment_name=f"segment_{seg_ix}",
                topo=ctx.ocn_topo,
                custom_segments=custom_segments,
            )
            segment.regrid_tides(
                tpxo_v,
                tpxo_u,
                tpxo_h,
                None,
                outfolder=ctx.output_path,
                startdate=date_range[0],
                repeat_year_forcing=False,
            )
