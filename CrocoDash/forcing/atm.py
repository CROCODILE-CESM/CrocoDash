"""Align data-model (DATM/DROF) forcing streams with the case's run dates.

CDEPS hardcodes ``year_align=1`` and the full year span for every JRA stream in
``stream_definition_{datm,drof}.xml``, and the ``DATM_YR_ALIGN``/``_START``/
``_END`` xml variables are only read by the CLM/GSWP3/NEON/CPLHIST stream sets
-- no JRA, NYF or ERA5 entry references them. So a JRA case silently reads an
arbitrary data year, and ``xmlchange`` cannot fix it. The only lever CDEPS
offers is ``user_nl_<comp>_streams``, which this configurator writes.

Narrowing the file list matters as much as the alignment: the ``<datafiles>``
list is expanded from the stream definition's own year tags *before* user mods
are merged, so retagging the years alone still leaves all 59 JRA files
enumerated, and CDEPS opens each one to build its time axis.
"""

from CrocoDash.forcing.base import *
from CrocoDash.forcing import cdeps_streams
from CrocoDash.logging import setup_logger

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

    def _plan(self, component, mode, cime_case, start_year, end_year):
        """Work out the stream mods for one component, or why there are none.

        Returns a record rather than raising: an unalignable component is
        reported and left at its CESM defaults, so a case that used to build
        still builds.
        """
        cesmroot = self.get_input_param("case_cesmroot")
        pad = self.get_input_param("stream_year_padding")
        narrow = self.get_input_param("narrow_stream_files")

        names = cdeps_streams.stream_names(cesmroot, component, mode)
        if not names:
            return {"status": "skipped", "reason": f"no streams defined for {mode}"}

        streams = {}
        for name in names:
            avail_first, avail_last = cdeps_streams.coverage(
                cesmroot, component, name, cime_case
            )
            # Single-year streams are climatologies (CORE2_NYF is 1/1/1, the
            # CORE_RYF*_JRA repeat years are e.g. 1961/1961). There is no
            # alignment to get right and no files to narrow.
            if avail_first == avail_last:
                return {
                    "status": "skipped",
                    "reason": f"{mode} is a single-year climatology",
                }
            if start_year < avail_first or end_year > avail_last:
                return {
                    "status": "skipped",
                    "reason": (
                        f"run years {start_year}-{end_year} fall outside the "
                        f"{avail_first}-{avail_last} covered by {mode}"
                    ),
                }

            # year_align == year_first makes the data year equal the model year
            # for every year in range: dYear = yrFirst + modulo(mYear - yrFirst, n).
            # The extra leading year is needed to interpolate at the run start.
            year_first = max(avail_first, start_year - 1 - pad)
            year_last = min(avail_last, end_year + pad)
            streams[name] = {
                "year_first": year_first,
                "year_last": year_last,
                "year_align": year_first,
            }
            if narrow:
                streams[name]["datafiles"] = cdeps_streams.datafiles(
                    cesmroot, component, name, year_first, year_last, cime_case
                )
        return {"status": "configured", "mode": mode, "streams": streams}

    def _apply(self, component, plan):
        """Write one component's mods to user_nl_<component>_streams.

        `append_user_nl` does no validation on its target, so passing
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
        append_user_nl(
            f"{component}_streams",
            pairs,
            do_exec=True,
            comment=(
                f"Align {plan['mode']} streams with the run dates "
                "(CrocoDash: CDEPS defaults to year_align=1)"
            ),
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
                plan = self._plan(component, mode, cime_case, start_year, end_year)

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
