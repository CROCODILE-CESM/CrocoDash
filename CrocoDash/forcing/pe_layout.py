"""Set the case's PE layout (NTASKS/ROOTPE) from how much ocean it has.

The PELayout configurator runs in configure_forcings() for every MOM6 case and
sets this layout:

- Every component starts at PE 0. The components share the same cores and
  take turns on them, so the case's run time is the sum of the components'
  times, and the job uses as many PEs as the largest count below.
- MOM6 gets one task per 170 ocean points, or one per 60 with MARBL (from
  tx2_3v3 benchmarks), counted from the topography file's mask. ``ntasks_ocn``
  given to the Case replaces this count.
- CICE and WW3, when the compset has them, get MOM6's count. They run on
  MOM6's grid and on its cores, so fewer tasks would only leave cores idle
  while they run. Their own cost is not benchmarked: the count is sized for
  MOM6 alone, so a case with CICE or WW3 runs slower than MOM6 alone would on
  the same count.
- The stub components (SICE, SWAV, SLND, SGLC) get MOM6's count too. They do
  no work, so the count costs nothing; it lets one NTASKS xmlchange set every
  component.
- DATM, DROF and the mediator get MOM6's count, raised to at least
  DATA_NTASKS (56) and capped at one node (MAX_MPITASKS_PER_NODE). On 4 tasks,
  reading the global JRA and GLOFAS streams took over an hour at startup in
  CrocoDashChecks' weekly Derecho runs. The cap keeps a case whose MOM6 fits
  on one node on one node. The runoff gets this count even when it's a stub
  (SROF).
- ESP keeps CIME's 1 task.

visualCaseGen has already run case.setup by the time forcings are configured,
and CIME won't build a case whose layout changed until ``case.setup --reset``
runs, so a change is followed by one. A reset also forces a rebuild, so it runs
only when the layout changed; xmlchanging a value to what it already is changes
nothing.
"""

import ast
import math
import subprocess
from pathlib import Path

import xarray as xr

from CrocoDash.forcing.base import *
from CrocoDash.logging import setup_logger

logger = setup_logger(__name__)

PTS_PER_TASK = 170
PTS_PER_TASK_MARBL = 60
DATA_NTASKS = 56


def pe_layout(ocean_points, tasks_per_node, marbl=False, ntasks_ocn=None):
    """{xml variable: value}, applied in this order: NTASKS and ROOTPE place
    every component, then DATM, DROF and the mediator get their own count."""
    if ntasks_ocn is None:
        ntasks_ocn = max(
            1,
            math.ceil(ocean_points / (PTS_PER_TASK_MARBL if marbl else PTS_PER_TASK)),
        )
    data = min(max(ntasks_ocn, DATA_NTASKS), tasks_per_node)
    return {
        "NTASKS": ntasks_ocn,
        "ROOTPE": 0,
        "NTASKS_ATM": data,
        "NTASKS_ROF": data,
        "NTASKS_CPL": data,
    }


@register
class PELayoutConfigurator(BaseConfigurator):
    name = "PELayout"
    allowed_compsets = ["MOM6"]

    input_params = [
        InputValueParam("case_caseroot", comment="Case directory"),
        InputFileParam("case_topo_path", comment="Ocean topography file"),
        InputValueParam("case_compset_lname", comment="Case compset"),
        InputValueParam(
            "case_ntasks_ocn",
            comment="MOM6 task count given to the Case, if any",
            optional=True,
        ),
    ]
    # In the order pe_layout() returns them: every component, then the data
    # components and the mediator.
    output_params = [
        XMLConfigParam("NTASKS", comment="Tasks for every component"),
        XMLConfigParam("ROOTPE", comment="First PE of every component"),
        XMLConfigParam("NTASKS_ATM", comment="DATM tasks"),
        XMLConfigParam("NTASKS_ROF", comment="DROF tasks"),
        XMLConfigParam("NTASKS_CPL", comment="Mediator tasks"),
    ]

    def __init__(
        self, case_caseroot, case_topo_path, case_compset_lname, case_ntasks_ocn=None
    ):
        super().__init__(
            case_caseroot=case_caseroot,
            case_topo_path=case_topo_path,
            case_compset_lname=case_compset_lname,
            case_ntasks_ocn=case_ntasks_ocn,
        )

    def configure(self):
        caseroot = self.get_input_param("case_caseroot")
        flags = ["--non-local"] if self.is_non_local else []
        if not Path(caseroot, "xmlquery").exists():
            raise RuntimeError(f"{caseroot} is not a CESM case directory")
        max_tasks_per_node = (
            subprocess.run(
                ["./xmlquery", "MAX_MPITASKS_PER_NODE", "--value", *flags],
                cwd=caseroot,
                capture_output=True,
                text=True,
                check=True,
            )
            .stdout.strip()
            .splitlines()[-1]
        )
        with xr.open_dataset(self.get_input_param("case_topo_path")) as topo:
            ocean_points = int(topo["mask"].sum())
        layout = pe_layout(
            ocean_points,
            int(max_tasks_per_node),
            marbl="%MARBL" in self.get_input_param("case_compset_lname"),
            ntasks_ocn=self.get_input_param("case_ntasks_ocn"),
        )
        # Compare against the locked copy of env_mach_pes.xml — that is what
        # CIME checks at build time. If a previous reset was interrupted, the
        # xmlchange is already in env_mach_pes.xml but not in the locked copy,
        # so reading env_mach_pes.xml would see "no change" and skip the reset.
        locked_file = "LockedFiles/env_mach_pes.xml"
        if not (Path(caseroot) / locked_file).exists():
            changed = True
        else:
            locked_values = {
                name: subprocess.run(
                    ["./xmlquery", name, "--value", "--file", locked_file, *flags],
                    cwd=caseroot,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                .stdout.strip()
                .splitlines()[-1]
                for name in ("NTASKS", "ROOTPE")
            }
            changed = any(
                int(value) != layout.get(f"{name}_{component}", layout[name])
                for name in ("NTASKS", "ROOTPE")
                for component, value in (
                    item.split(":") for item in ast.literal_eval(locked_values[name])
                )
                if component != "ESP"
            )
        for name, value in layout.items():
            self.set_output_param(name, value)
        super().configure()
        if changed:
            out = subprocess.run(
                ["./case.setup", "--reset", *flags],
                cwd=caseroot,
                capture_output=True,
                text=True,
            )
            if out.returncode != 0:
                raise RuntimeError(
                    f"case.setup --reset failed in {caseroot}:\n{out.stderr}"
                )
            logger.info(
                "PE layout from %s ocean points: MOM6 and every other model "
                "component (CICE, WW3 and the stubs) on %s tasks, DATM, DROF "
                "and the mediator on %s, all from PE 0; ran case.setup --reset",
                ocean_points,
                layout["NTASKS"],
                layout["NTASKS_ATM"],
            )
