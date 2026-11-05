"""Set the case's PE layout (NTASKS/ROOTPE) from how much ocean it has.

MOM6 needs about 170 ocean points per task, 60 with MARBL (from tx2_3v3
benchmarks). A domain that needs no more tasks than the largest of SMALL_TIERS
runs on one node, every component from PE 0: MOM6 on the smallest tier that
fits, everything else on one task. A bigger one gets MOM_interface's regional
S, M or L tier: the other components fill node 0, MOM6 the whole nodes after
it. ``ntasks_ocn`` on the Case replaces the count. The wave model, active or
stub, goes with the other components.

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
# MOM6 task counts for a domain that fits on one node, shared with the rest.
# 1 is MOM_interface's default regional layout (XS).
SMALL_TIERS = (1, 16, 32, 64)
# MOM_interface's regional S/M/L tiers for Derecho (cime_config/config_pes.xml,
# branch regional_changes_for_croc at b51a8c6), as the number of whole nodes
# MOM6 gets after node 0: MOM6 on 128, 384 and 896 tasks, or 384, 1152 and
# 2560 with MARBL. A domain needing one node of MOM6 tasks gets S, up to three
# M, more L.
MOM6_NODES = {"S": 1, "M": 3, "L": 7}
MOM6_NODES_MARBL = {"S": 3, "M": 9, "L": 20}


def pe_layout(ocean_points, tasks_per_node, marbl=False, ntasks_ocn=None):
    """{xml variable: value}, applied in this order: NTASKS and ROOTPE place
    every component, then NTASKS_OCN and ROOTPE_OCN move MOM6."""
    small = [n for n in SMALL_TIERS if n <= tasks_per_node]
    if ntasks_ocn is None:
        needed = math.ceil(
            ocean_points / (PTS_PER_TASK_MARBL if marbl else PTS_PER_TASK)
        )
        ntasks_ocn = next((n for n in small if n >= needed), None)
        if ntasks_ocn is None:
            nodes = math.ceil(needed / tasks_per_node)
            size = "S" if nodes == 1 else "M" if nodes <= 3 else "L"
            ntasks_ocn = (MOM6_NODES_MARBL if marbl else MOM6_NODES)[size]
            ntasks_ocn *= tasks_per_node
    if ntasks_ocn <= small[-1]:
        return {"NTASKS": 1, "ROOTPE": 0, "NTASKS_OCN": ntasks_ocn, "ROOTPE_OCN": 0}
    return {
        "NTASKS": tasks_per_node,
        "ROOTPE": 0,
        "NTASKS_OCN": ntasks_ocn,
        "ROOTPE_OCN": tasks_per_node,
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
    # In the order pe_layout() returns them: every component, then MOM6.
    output_params = [
        XMLConfigParam("NTASKS", comment="Tasks for every component"),
        XMLConfigParam("ROOTPE", comment="First PE of every component"),
        XMLConfigParam("NTASKS_OCN", comment="MOM6 tasks"),
        XMLConfigParam("ROOTPE_OCN", comment="MOM6's first PE"),
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
        # e.g. "128", or "['CPL:128', 'ATM:128', 'OCN:128', ..., 'ESP:1']"
        case_values = {
            name: subprocess.run(
                ["./xmlquery", name, "--value", *flags],
                cwd=caseroot,
                capture_output=True,
                text=True,
                check=True,
            )
            .stdout.strip()
            .splitlines()[-1]
            for name in ("MAX_TASKS_PER_NODE", "NTASKS", "ROOTPE")
        }
        with xr.open_dataset(self.get_input_param("case_topo_path")) as topo:
            ocean_points = int(topo["mask"].sum())
        layout = pe_layout(
            ocean_points,
            int(case_values["MAX_TASKS_PER_NODE"]),
            marbl="%MARBL" in self.get_input_param("case_compset_lname"),
            ntasks_ocn=self.get_input_param("case_ntasks_ocn"),
        )
        # Whether any component, ESP aside, has other NTASKS or ROOTPE now.
        changed = any(
            int(value) != layout[f"{name}_OCN" if component == "OCN" else name]
            for name in ("NTASKS", "ROOTPE")
            for component, value in (
                item.split(":") for item in ast.literal_eval(case_values[name])
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
                "PE layout: MOM6 on %s tasks from PE %s, the other components on %s "
                "(%s ocean points); ran case.setup --reset",
                layout["NTASKS_OCN"],
                layout["ROOTPE_OCN"],
                layout["NTASKS"],
                ocean_points,
            )
