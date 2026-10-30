"""The data atmosphere: a JRA or CORE2 IAF DATM reads the run's own years of
its forcing (see forcing.utils.set_stream_years). Runoff does the same for DROF."""

from CrocoDash.forcing.base import *
from CrocoDash.forcing.utils import set_stream_years


@register
class DATMConfigurator(BaseConfigurator):
    name = "DATM"
    required_for_compsets = ["DATM%JRA", "DATM%IAF"]
    allowed_compsets = ["DATM"]

    input_params = []
    output_params = [
        ConfigOutputParam(
            "stream_years",
            comment="The DATM_YR_* values set ({}: left at the CESM defaults)",
        ),
    ]

    def __init__(self):
        super().__init__()

    def configure(self):
        case = getattr(self.registry, "case", None)
        self.set_output_param("stream_years", set_stream_years(case, "datm"))
        super().configure()
