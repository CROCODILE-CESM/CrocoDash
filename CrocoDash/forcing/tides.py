from pathlib import Path

import regional_mom6 as rmom6
from CrocoDash.vgrid import VGrid
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
        # hgrid_type/vgrid_type take mom6_forge Grid/VGrid objects directly --
        # "from_file" + a separate hgrid_path/vgrid_path kwarg no longer
        # exists; "from_file" instead means "lazily read mom_input_dir/
        # hgrid.nc", which isn't this experiment's own supergrid filename.
        expt = rmom6.experiment(
            date_range=("1850-01-01 00:00:00", "1851-01-01 00:00:00"),  # Dummy times
            resolution=None,
            number_vertical_layers=None,
            layer_thickness_ratio=None,
            depth=ctx.ocn_topo.max_depth,
            mom_run_dir=ctx.inputdir,
            mom_input_dir=ctx.output_path,
            hgrid_type=ctx.grid,
            vgrid_type=VGrid.from_file(str(ctx.vgrid_path)),
            minimum_depth=ctx.ocn_topo.min_depth,
            tidal_constituents=self.get_input_param("tidal_constituents"),
            expt_name="tides",
            boundaries=self.get_input_param("boundaries"),
        )
        expt.setup_boundary_tides(
            tpxo_elevation_filepath=self.get_input_param("tpxo_elevation_filepath"),
            tpxo_velocity_filepath=self.get_input_param("tpxo_velocity_filepath"),
            tidal_constituents=self.get_input_param("tidal_constituents"),
        )
