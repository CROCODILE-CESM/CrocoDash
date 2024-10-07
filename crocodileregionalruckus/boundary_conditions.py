from pathlib import Path
from .rm6_dir import regional_mom6 as rm6


class BoundaryConditions:
    def __init__(self, others=None):
        self.boundary_condition_gen = rm6.experiment.create_empty()
        return

    def generate_initial_conditions(self, glorys_):
        # Define a mapping from the GLORYS variables and dimensions to the MOM6 ones
        ocean_varnames = {
            "time": "time",
            "yh": "latitude",
            "xh": "longitude",
            "zl": "depth",
            "eta": "zos",
            "u": "uo",
            "v": "vo",
            "tracers": {"salt": "so", "temp": "thetao"},
        }
        # Define the path to the GLORYS data
        glorys_path = "/path/to/glorys/data"
        self.boundary_condition_gen.setup_initial_condition(
            Path(glorys_path)
            / "ic_unprocessed.nc",  # directory where the unprocessed initial condition is stored, as defined earlier
            ocean_varnames,
            arakawa_grid="A",
        )
        return

    def generate_rectangular_boundary_conditions(self):
        self.boundary_condition_gen.setup_ocean_state_boundaries()
        self.boundary_condition_gen.setup_boundary_tides()

    def setup_MOM_files(self):
        self.boundary_condition_gen.setup_run_directory(
            surface_forcing="jra", with_tides_rectangular=True, overwrite=True
        )


