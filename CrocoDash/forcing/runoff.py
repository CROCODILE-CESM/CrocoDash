from pathlib import Path

from mom6_forge import mapping

from CrocoDash.forcing.base import *

# Where process() writes the runoff maps, relative to the case inputdir.
MAPPING_SUBDIR = "mapping"


@register
class RunoffConfigurator(BaseConfigurator):
    name = "Runoff"
    process_components = {"runoff": "process"}
    required_for_compsets = {"DROF"}
    allowed_compsets = {"DROF"}
    input_params = [
        InputValueParam("case_grid_name", comment="Case grid name"),
        InputValueParam("case_session_id", comment="Case session identifier"),
        InputValueParam("case_compset_lname", comment="Case compset"),
        InputValueParam("case_inputdir", comment="Case input directory"),
        InputValueParam(
            "rmax",
            comment=(
                "Smoothing radius (km) for runoff mapping generation; "
                "suggested from the ocean grid if unset"
            ),
        ),
        InputValueParam(
            "fold",
            comment=(
                "Smoothing fold distance (km) for runoff mapping generation; "
                "suggested from the ocean grid if unset"
            ),
        ),
        InputFileParam("case_esmf_mesh_path", comment="Ocean ESMF Mesh File Path"),
    ]
    output_params = [
        ConfigOutputParam("rof_grid_name", comment="The case's runoff grid (ROF_GRID)"),
        ConfigOutputParam(
            "rof_esmf_mesh_filepath",
            comment="The case's runoff ESMF mesh (ROF_DOMAIN_MESH)",
        ),
        XMLConfigParam(
            "ROF2OCN_LIQ_RMAPNAME",
            comment="Runoff to ocean liquid runoff mapping file",
        ),
        XMLConfigParam(
            "ROF2OCN_ICE_RMAPNAME",
            comment="Runoff to ocean ice runoff mapping file",
        ),
    ]

    def __init__(
        self,
        case_grid_name,
        case_session_id,
        case_compset_lname,
        case_inputdir,
        case_esmf_mesh_path,
        rmax=None,
        fold=None,
    ):
        """
        rmax : float, optional
            If passed, specifies the smoothing radius (in km) for runoff mapping generation.
            If not provided, a suggested value based on the ocean grid will be used.
        fold : float, optional
            If passed, specifies the smoothing fold distance (in km) for runoff mapping generation.
            If not provided, a suggested value based on the ocean grid will be used.
        """
        super().__init__(
            case_grid_name=case_grid_name,
            case_session_id=case_session_id,
            case_inputdir=case_inputdir,
            rmax=rmax,
            fold=fold,
            case_compset_lname=case_compset_lname,
            case_esmf_mesh_path=case_esmf_mesh_path,
        )

    def configure(self):
        # The map takes runoff from the case's own runoff grid, as it is now:
        # to use another one (e.g. a subset of the runoff data), set the case's
        # ROF_GRID / ROF_DOMAIN_MESH. A grid the case doesn't run on would give
        # the coupler a map that doesn't match.
        caseroot = self.registry.case.caseroot
        for output, var in (
            ("rof_grid_name", "ROF_GRID"),
            ("rof_esmf_mesh_filepath", "ROF_DOMAIN_MESH"),
        ):
            self.set_output_param(
                output,
                xmlquery(var, caseroot=caseroot, is_non_local=self.is_non_local),
            )
        runoff_mapping_file_nnsm = f"glofas_{self.get_input_param('case_grid_name')}_{self.get_input_param('case_session_id')}_nnsm.nc"
        rof_case_grid_name = self.get_output_param("rof_grid_name")
        mapping_file_prefix = (
            f"{rof_case_grid_name}_to_{self.get_input_param('case_grid_name')}_map"
        )
        mapping_dir = Path(self.get_input_param("case_inputdir")) / MAPPING_SUBDIR

        if self.get_input_param("rmax") is None:
            rmax, fold = mapping.get_suggested_smoothing_params(
                self.get_input_param("case_esmf_mesh_path")
            )
            self.set_input_param("rmax", rmax)
            self.set_input_param("fold", fold)
        self.runoff_mapping_file_nnsm = mapping.get_smoothed_map_filepath(
            mapping_file_prefix=mapping_file_prefix,
            output_dir=mapping_dir,
            rmax=self.get_input_param("rmax"),
            fold=self.get_input_param("fold"),
        )
        self.set_output_param("ROF2OCN_LIQ_RMAPNAME", self.runoff_mapping_file_nnsm)
        self.set_output_param("ROF2OCN_ICE_RMAPNAME", self.runoff_mapping_file_nnsm)
        super().configure()

    def validate_args(self, **kwargs):
        super().validate_args(**kwargs)
        if (kwargs["rmax"] is None) != (kwargs["fold"] is None):
            raise ValueError("Both rmax and fold must be specified together.")
        if kwargs["rmax"] is not None:
            assert "SROF" not in kwargs["case_compset_lname"], (
                "When rmax and fold are specified, "
                "the compset must include an active or data runoff model."
            )

    def output_files(self, ctx):
        # The liquid and ice maps are the same file. Named by basename rather
        # than the stored absolute path, so a relocated inputdir still matches.
        map_name = Path(self.get_output_param("ROF2OCN_LIQ_RMAPNAME")).name
        return {"runoff": [ctx.inputdir / MAPPING_SUBDIR / map_name]}

    def process(self, ctx):
        """Generate runoff-to-ocean mapping files if runoff is active in the compset."""
        rof_grid_name = self.get_output_param("rof_grid_name")
        rof_esmf_mesh_filepath = self.get_output_param("rof_esmf_mesh_filepath")
        ocn_mesh_filepath = self.get_input_param("case_esmf_mesh_path")
        grid_name = self.get_input_param("case_grid_name")
        rmax = self.get_input_param("rmax")
        fold = self.get_input_param("fold")

        if not rof_grid_name or not rof_esmf_mesh_filepath:
            raise ValueError(
                "config.json has no runoff grid or mesh for this case; rerun "
                "configure_forcings() to record them."
            )

        mapping_file_prefix = f"{rof_grid_name}_to_{grid_name}_map"
        mapping_dir = ctx.inputdir / MAPPING_SUBDIR
        mapping_dir.mkdir(exist_ok=True)

        runoff_mapping_file_nnsm = mapping.get_smoothed_map_filepath(
            mapping_file_prefix=mapping_file_prefix,
            output_dir=mapping_dir,
            rmax=int(rmax),
            fold=int(fold),
        )

        if not runoff_mapping_file_nnsm.exists():
            print("Creating runoff mapping file(s)...")
            print(ocn_mesh_filepath)
            mapping.gen_rof_maps(
                rof_mesh_path=rof_esmf_mesh_filepath,
                ocn_mesh_path=ocn_mesh_filepath,
                output_dir=mapping_dir,
                mapping_file_prefix=mapping_file_prefix,
                rmax=int(rmax),
                fold=int(fold),
            )
        else:
            print(
                f"Runoff mapping file {runoff_mapping_file_nnsm} already exists, reusing it."
            )
