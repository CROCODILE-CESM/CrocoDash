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

    def _run(self, *cmd):
        """Run a case script in the caseroot; its last line of output."""
        cmd = list(cmd) + (["--non-local"] if self.is_non_local else [])
        caseroot = self.get_input_param("case_caseroot")
        try:
            out = subprocess.run(cmd, cwd=caseroot, capture_output=True, text=True)
        except FileNotFoundError as e:
            raise RuntimeError(f"{caseroot} is not a CESM case directory") from e
        if out.returncode != 0:
            raise RuntimeError(
                f"{' '.join(cmd)} failed in {caseroot}:\n{out.stderr or out.stdout}"
            )
        return out.stdout.strip().splitlines()[-1] if out.stdout.strip() else ""

    def _has_layout(self, layout):
        """Whether every component already has the layout's NTASKS and ROOTPE."""
        for name in ("NTASKS", "ROOTPE"):
            # e.g. ['CPL:128', 'ATM:128', 'OCN:128', ..., 'ESP:1']
            current = dict(
                item.split(":")
                for item in ast.literal_eval(self._run("./xmlquery", name, "--value"))
            )
            current.pop("ESP", None)
            for component, value in current.items():
                wanted = layout[f"{name}_OCN" if component == "OCN" else name]
                if int(value) != wanted:
                    return False
        return True

    def configure(self):
        tasks_per_node = int(self._run("./xmlquery", "MAX_TASKS_PER_NODE", "--value"))
        with xr.open_dataset(self.get_input_param("case_topo_path")) as topo:
            ocean_points = int(topo["mask"].sum())
        layout = pe_layout(
            ocean_points,
            tasks_per_node,
            marbl="%MARBL" in self.get_input_param("case_compset_lname"),
            ntasks_ocn=self.get_input_param("case_ntasks_ocn"),
        )
        changed = not self._has_layout(layout)
        for name, value in layout.items():
            self.set_output_param(name, value)
        super().configure()
        if changed:
            self._run("./case.setup", "--reset")
            logger.info(
                "PE layout: MOM6 on %s tasks from PE %s, the other components on %s "
                "(%s ocean points); ran case.setup --reset",
                layout["NTASKS_OCN"],
                layout["ROOTPE_OCN"],
                layout["NTASKS"],
                ocean_points,
            )
