from pathlib import Path

from mom6_forge import mapping
from ProConPy.config_var import cvars

from CrocoDash.forcing.base import *


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
            "rmax", comment="Smoothing radius (in meters) for runoff mapping generation"
        ),
        InputValueParam(
            "rof_grid_name", comment="Name of the runoff grid used in the case"
        ),
        InputValueParam(
            "fold", comment="Smoothing fold parameter for runoff mapping generation"
        ),
        InputFileParam("rof_esmf_mesh_filepath", comment="Runoff ESMF Mesh File Path"),
        InputFileParam("case_esmf_mesh_path", comment="Ocean ESMF Mesh File Path"),
    ]
    output_params = [
        XMLConfigParam(
            "ROF2OCN_LIQ_RMAPNAME",
            comment="Runoff to ocean liquid runoff mapping file",
            is_file=True,
        ),
        XMLConfigParam(
            "ROF2OCN_ICE_RMAPNAME",
            comment="Runoff to ocean ice runoff mapping file",
            is_file=True,
        ),
    ]

    def __init__(
        self,
        case_grid_name,
        case_session_id,
        case_compset_lname,
        case_inputdir,
        case_esmf_mesh_path,
        case_cime=None,
        rmax=None,
        fold=None,
        rof_grid_name=None,
        rof_esmf_mesh_filepath=None,
    ):
        """
        rmax : float, optional
            If passed, specifies the smoothing radius (in meters) for runoff mapping generation.
            If not provided, a suggested value based on the ocean grid will be used.
        fold : float, optional
            If passed, specifies the smoothing fold parameter for runoff mapping generation.
            If not provided, a suggested value based on the ocean grid will be used.
        """
        if case_cime is not None:
            if rof_esmf_mesh_filepath is None:
                rof_esmf_mesh_filepath = case_cime.get_mesh_path(
                    "rof", cvars["CUSTOM_ROF_GRID"].value
                )
            if rof_grid_name is None:
                rof_grid_name = cvars["CUSTOM_ROF_GRID"].value
            super().__init__(
                case_grid_name=case_grid_name,
                case_session_id=case_session_id,
                case_inputdir=case_inputdir,
                rmax=rmax,
                fold=fold,
                case_esmf_mesh_path=case_esmf_mesh_path,
                case_compset_lname=case_compset_lname,
                rof_esmf_mesh_filepath=rof_esmf_mesh_filepath,
                rof_grid_name=rof_grid_name,
            )
        else:
            super().__init__(
                case_grid_name=case_grid_name,
                case_session_id=case_session_id,
                case_inputdir=case_inputdir,
                rmax=rmax,
                fold=fold,
                case_compset_lname=case_compset_lname,
                case_esmf_mesh_path=case_esmf_mesh_path,
                rof_esmf_mesh_filepath=rof_esmf_mesh_filepath,
                rof_grid_name=rof_grid_name,
            )

    def configure(self):
        runoff_mapping_file_nnsm = f"glofas_{self.get_input_param('case_grid_name')}_{self.get_input_param('case_session_id')}_nnsm.nc"
        rof_case_grid_name = self.get_input_param("rof_grid_name")
        mapping_file_prefix = (
            f"{rof_case_grid_name}_to_{self.get_input_param('case_grid_name')}_map"
        )
        mapping_dir = Path(self.get_input_param("case_inputdir")) / "mapping"

        if self.get_input_param("rmax") is None:
            rmax, fold = mapping.get_suggested_smoothing_params(
                self.get_input_param("rof_esmf_mesh_filepath")
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

        if (kwargs["rmax"] is None) != (kwargs["fold"] is None):
            raise ValueError("Both rmax and fold must be specified together.")
        if kwargs["rmax"] is not None:
            assert "SROF" not in kwargs["case_compset_lname"], (
                "When rmax and fold are specified, "
                "the compset must include an active or data runoff model."
            )

    def get_output_filepaths(self, ocn_ice_directory):
        # Return just the xml file paths (Can be either direct path or in ocn_ice as well)
        ocn_ice_directory = Path(ocn_ice_directory)

        params = [
            self.get_output_param("ROF2OCN_LIQ_RMAPNAME"),
            self.get_output_param("ROF2OCN_ICE_RMAPNAME"),
        ]

        valid_paths = []
        for p in params:
            if not p:
                continue
            p_path = Path(p)
            if not p_path.exists():
                p_path = ocn_ice_directory / p_path.name
            if p_path.exists():
                valid_paths.append(str(p_path.resolve()))

        return valid_paths

    def process(self, ctx):
        """Generate runoff-to-ocean mapping files if runoff is active in the compset."""
        rof_grid_name = self.get_input_param("rof_grid_name")
        rof_esmf_mesh_filepath = self.get_input_param("rof_esmf_mesh_filepath")
        ocn_mesh_filepath = self.get_input_param("case_esmf_mesh_path")
        grid_name = self.get_input_param("case_grid_name")
        rmax = self.get_input_param("rmax")
        fold = self.get_input_param("fold")

        assert rof_grid_name is not None, "Couldn't determine runoff grid name."
        assert rof_esmf_mesh_filepath != "", "Runoff ESMF mesh path could not be found."

        mapping_file_prefix = f"{rof_grid_name}_to_{grid_name}_map"
        mapping_dir = ctx.inputdir / "mapping"
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
