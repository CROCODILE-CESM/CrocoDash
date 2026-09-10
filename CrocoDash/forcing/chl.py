from pathlib import Path

from mom6_forge import chl as m6f_chl

from CrocoDash.forcing.base import *
from CrocoDash.raw_data_access.base import Calendar


@register
class ChlConfigurator(BaseConfigurator):
    name = "Chl"
    process_components = {"chl": "process"}
    forbidden_compsets = ["MARBL"]
    input_params = [
        InputFileParam(
            "chl_processed_filepath",
            comment="NetCDF file containing processed chlorophyll data",
        ),
        InputValueParam("case_grid_name", comment="Case grid name"),
        InputValueParam("case_session_id", comment="Case session identifier"),
        InputValueParam(
            "calendar",
            comment="Calendar names (cf/cesm/mom6) for the chlorophyll output",
        ),
    ]
    output_params = [
        UserNLConfigParam(
            "CHL_FILE",
            comment="Chlorophyll data file",
            user_nl_name="mom",
            is_file=True,
        ),
        UserNLConfigParam(
            "CHL_FROM_FILE", comment="Enable chlorophyll from file", user_nl_name="mom"
        ),
        UserNLConfigParam(
            "VAR_PEN_SW",
            comment="Enable variable penetration for shortwave",
            user_nl_name="mom",
        ),
        UserNLConfigParam(
            "PEN_SW_NBANDS",
            comment="Number of shortwave penetration bands",
            user_nl_name="mom",
        ),
    ]

    def __init__(
        self,
        chl_processed_filepath,
        case_grid_name,
        case_session_id,
        case_forcing_product=None,
        calendar=None,
    ):
        if calendar is None and case_forcing_product is not None:
            calendar = case_forcing_product.calendar

        super().__init__(
            chl_processed_filepath=chl_processed_filepath,
            case_grid_name=case_grid_name,
            case_session_id=case_session_id,
            calendar=calendar_as_dict(calendar),
        )

    def validate_args(self, **kwargs):
        if not Path(kwargs["chl_processed_filepath"]).exists():
            raise FileNotFoundError(
                f"Chlorophyll file {kwargs['chl_processed_filepath']} does not exist."
            )

    def configure(self):
        regional_chl_file_path = (
            f"seawifs-clim-1997-2010-{self.get_input_param('case_grid_name')}.nc"
        )
        self.set_output_param("CHL_FILE", regional_chl_file_path)
        self.set_output_param("CHL_FROM_FILE", "TRUE")
        self.set_output_param("VAR_PEN_SW", "TRUE")
        self.set_output_param("PEN_SW_NBANDS", 3)
        super().configure()

    def process(self, ctx):
        m6f_chl.interpolate_and_fill_seawifs(
            ctx.grid,
            ctx.ocn_topo,
            self.get_input_param("chl_processed_filepath"),
            ctx.output_path / self.get_output_param("CHL_FILE"),
            # mom6_forge stamps this straight onto the output time coordinate,
            # which MOM6/FMS then reads, so it needs the mom6 spelling.
            calendar=Calendar(**self.get_input_param("calendar")).mom6,
        )
