"""Align data-model (DATM/DROF) forcing streams with the case's run dates.

CDEPS reads every JRA stream with ``year_align=1`` and the dataset's full year
span, so a JRA case silently reads an arbitrary data year, and only
``user_nl_<comp>_streams`` can change that. visualCaseGen's
``plan_stream_years`` works out the settings for the run; this configurator
writes them into CrocoDash's block in each component's streams file.
"""

from CrocoDash.forcing.base import *
from CrocoDash.logging import setup_logger
from visualCaseGen import user_nl_blocks
from visualCaseGen.stream_years import plan_stream_years

logger = setup_logger(__name__)

# The data-model components whose streams are year-dependent, and the xml
# variable naming the active stream set for each.
_COMPONENTS = {"datm": "DATM_MODE", "drof": "DROF_MODE"}


@register
class StreamYearConfigurator(BaseConfigurator):
    name = "StreamYears"
    required_for_compsets = ["DATM%JRA"]
    allowed_compsets = ["DATM"]

    _DATE_FORMAT = "%Y%m%d"

    input_params = [
        InputValueParam("case_cesmroot", comment="CESM root directory"),
        InputValueParam("start_date", comment="Forcing start date"),
        InputValueParam("end_date", comment="Forcing end date"),
        InputValueParam(
            "stream_year_padding",
            comment="Extra years of forcing kept either side of the run",
        ),
        InputValueParam(
            "narrow_stream_files",
            comment="Restrict each stream's file list to the years the run needs",
        ),
    ]
    output_params = [
        ConfigOutputParam(
            "datm_streams", comment="Stream year mods applied to user_nl_datm_streams"
        ),
        ConfigOutputParam(
            "drof_streams", comment="Stream year mods applied to user_nl_drof_streams"
        ),
    ]

    def __init__(
        self,
        case_cesmroot,
        date_range=None,
        start_date=None,
        end_date=None,
        stream_year_padding=1,
        narrow_stream_files=True,
    ):
        if date_range is not None:
            start_date = date_range[0].strftime(self._DATE_FORMAT)
            end_date = date_range[1].strftime(self._DATE_FORMAT)
        super().__init__(
            case_cesmroot=case_cesmroot,
            start_date=start_date,
            end_date=end_date,
            stream_year_padding=stream_year_padding,
            narrow_stream_files=narrow_stream_files,
        )

    def _apply(self, component, plan):
        """Write one component's mods to user_nl_<component>_streams.

        `user_nl_blocks.write` does no validation on its target, so passing
        "datm_streams" writes user_nl_datm_streams, and each pair is formatted
        as `name = value` -- exactly the `<stream>:<key> = <value>` syntax
        CDEPS's stream parser expects.
        """
        pairs = []
        for name, mods in plan["streams"].items():
            for key in ("year_first", "year_last", "year_align"):
                pairs.append((f"{name}:{key}", mods[key]))
            if "datafiles" in mods:
                pairs.append((f"{name}:datafiles", ",".join(mods["datafiles"])))
        comment = (
            f"Align {plan['mode']} streams with the run dates "
            "(CrocoDash: CDEPS defaults to year_align=1)"
        )
        case = self.registry.case
        user_nl_blocks.write(
            self.name,
            f"{component}_streams",
            [(comment, pairs)],
            caseroot=case.caseroot,
            ninst=case.ninst,
            tag=USER_NL_TAG,
        )

    def configure(self):
        start_year = int(self.get_input_param("start_date")[:4])
        end_year = int(self.get_input_param("end_date")[:4])

        # The live CIME Case is what names the active stream set and expands
        # $DIN_LOC_ROOT. It is always there when run_configurators drives us;
        # outside that flow (deserialize, inspect) there is no case, and so
        # nothing we can determine.
        case = getattr(getattr(self, "registry", None), "case", None)
        cime_case = getattr(case, "_cime_case", None)

        for component in _COMPONENTS:
            mode = cime_case.get_value(_COMPONENTS[component]) if cime_case else None
            if cime_case is None:
                plan = {
                    "status": "skipped",
                    "reason": "no CESM case available to read the stream mode from",
                }
            elif not mode:
                plan = {"status": "skipped", "reason": f"no active {component}"}
            else:
                plan = plan_stream_years(
                    self.get_input_param("case_cesmroot"),
                    component,
                    mode,
                    cime_case,
                    start_year,
                    end_year,
                    padding=self.get_input_param("stream_year_padding"),
                    narrow=self.get_input_param("narrow_stream_files"),
                )

            if plan["status"] == "configured":
                self._apply(component, plan)
            else:
                logger.warning(
                    "%s stream years left at CESM defaults: %s",
                    component.upper(),
                    plan["reason"],
                )
            self.set_output_param(f"{component}_streams", plan)

        super().configure()
