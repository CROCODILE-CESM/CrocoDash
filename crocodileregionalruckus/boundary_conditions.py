import logging
bc_logger = logging.getLogger(__name__)
from pathlib import Path
from .rm6_dir import regional_mom6 as rm6
import os
import shutil
import xarray as xr

class BoundaryConditions:
    @property
    def initial_condition(self):
        try:
            datasets = []
            for path in self._init_cond_paths:
                datasets.append( xr.open_dataset(path))
        except:
            return "Unable to access initial condition files"

    @initial_condition.setter
    def initial_condition(self, value):
        bc_logger.warning("Make sure the input value is in the form of trhee dataset list of the form init_vel, init_eta, nit_tracers")
        try:
            for ds in value:
                ds.to_netcdf(self._init_cond_paths[value.index(ds)])

        except:
            return "Unable to save initial condition files make sure it is list with vel, eta, and tracers"
        
    @property
    def ocean_state_boundaries(self):
        return "Not Supported"

    @property
    def boundary_tides(self):
        return "Not Supported"

    def __init__(self,
        delete_temp_storage=True):
        self.delete_temp_storage = delete_temp_storage
        # Create a temporary storage directory to offload heavy memory items.
        self.temp_storage = ".crr_bcc_temp"
        os.makedirs(self.temp_storage, exist_ok=True)
        self._init_cond_paths = [Path(self.temp_storage) /"forcing"/"init_vel.nc", Path(self.temp_storage) /"forcing"/"init_eta.nc", Path(self.temp_storage) /"forcing"/"init_tracers.nc"]
        return
    
    def __del__(self):
        if self.delete_temp_storage:
            try:
                shutil.rmtree(self.temp_storage)
            except:
                print("Error cleaning up CRR grid_gen temp storage directory.")

    def setup_initial_condition(self,hgrid, vgrid, glorys_path, ocean_varnames, arakawa_grid = "A"):
        # Define a mapping from the GLORYS variables and dimensions to the MOM6 ones
        expt = rm6.experiment.create_empty()
        expt.hgrid = hgrid
        expt.vgrid = vgrid
        expt.mom_input_dir = Path(self.temp_storage)
        os.makedirs(expt.mom_input_dir /"forcing", exist_ok=True)
        expt.setup_initial_condition(
            glorys_path,  # directory where the unprocessed initial condition is stored, as defined earlier
            ocean_varnames,
            arakawa_grid="A",
        )
        self._init_cond_paths = [expt.mom_input_dir /"forcing"/"init_vel.nc", expt.mom_input_dir /"forcing"/"init_eta.nc", expt.mom_input_dir /"forcing"/"init_tracers.nc"]
        return

    def get_glorys_rectangular(self,raw_boundaries_path, boundaries):
        expt = rm6.experiment.create_empty()
        return expt.get_glorys_rectangular(raw_boundaries_path, boundaries)

    
    def setup_ocean_state_boundaries(self, hgrid, vgrid, start_date,     glorys_path,
        ocean_varnames,
        boundaries,
        arakawa_grid = "A",
         repeat_year_forcing = False):
        expt = rm6.experiment.create_empty()
        expt.hgrid = hgrid
        expt.vgrid = vgrid
        expt.date_range = [start_date, None]
        expt.repeat_year_forcing = repeat_year_forcing
        expt.mom_input_dir = Path(self.temp_storage)
        os.makedirs(expt.mom_input_dir /"weights", exist_ok=True)
        expt.setup_ocean_state_boundaries(
            glorys_path,  # directory where the unprocessed initial condition is stored, as defined earlier
            ocean_varnames,
            boundaries,
            arakawa_grid=arakawa_grid,
        )
        return
    
    def setup_boundary_tides(self, hgrid, start_date,tidal_consituents, path_td, tidal_filename,
         repeat_year_forcing = False):
        
        expt = rm6.experiment.create_empty()
        expt.hgrid = hgrid
        expt.date_range = [start_date, None]
        expt.repeat_year_forcing = repeat_year_forcing
        expt.mom_input_dir = Path(self.temp_storage)
        os.makedirs(expt.mom_input_dir /"forcing", exist_ok=True)
        expt.setup_boundary_tides(path_to_td=path_td, tidal_filename=tidal_filename, tidal_constituents=tidal_consituents)
        return
    
    def export_files(self, output_folder):
        """
        Export all files from the temp_storage directory to the output_folder.

        Parameters:
        output_folder (str): Path to the output directory where files will be copied.
        """
        input_dir = Path(self.temp_storage)
        output_dir = Path(output_folder)

        if not output_dir.exists():
            os.makedirs(output_dir)

        for item in input_dir.iterdir():
            if item.is_file():
                shutil.copy(item, output_dir / item.name)
            elif item.is_dir():
                shutil.copytree(item, output_dir / item.name)

        print(f"All files have been exported to {output_folder}")


