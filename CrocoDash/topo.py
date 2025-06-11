import xarray as xr

from mom6_bathy.topo import Topo as mom6_bathy_Topo
import regional_mom6 as rmom6
from pathlib import Path


class Topo(mom6_bathy_Topo):
    
    def __init__(self, grid, min_depth):
        
        # Initialize inherited attributes from mom6_bathy Topo object
        super().__init__(grid = grid, min_depth=min_depth)
        
        # Add additional regional_mom6 experiment attribute
        self.expt = None
    
    def _setup_rm6_experiment(self, write_directory=Path("")):
        expt = rmom6.experiment.create_empty()

        # Note: What regional_mom6 calls the hgrid is actually the supergrid
        class HGrid:
            pass

        expt.hgrid = HGrid()
        expt.hgrid.x = xr.DataArray(self._grid._supergrid.x, dims=("nyp", "nxp"))
        expt.hgrid.y = xr.DataArray(self._grid._supergrid.y, dims=("nyp", "nxp"))
        expt.latitude_extent = [
            self._grid._supergrid.y.min(),
            self._grid._supergrid.y.max(),
        ]
        expt.longitude_extent = [
            self._grid._supergrid.x.min(),
            self._grid._supergrid.x.max(),
        ]

        expt.mom_input_dir = write_directory
        
        # Return expt object
        return expt

    def interpolate_from_file(
        self,
        *,
        file_path,
        longitude_coordinate_name,
        latitude_coordinate_name,
        vertical_coordinate_name,
        fill_channels=False,
        positive_down=False,
        write_to_file=False,
        write_directory = Path(""),
    ):
        
        self.expt = self._setup_rm6_experiment(write_directory)
                 
        print(
            """**NOTE**
            If bathymetry setup fails (e.g. kernel crashes), restart the kernel and edit this cell.
            Call ``topo.mpi_interpolate_from_file()`` instead. Follow the given instructions for using mpi 
            and ESMF_Regrid outside of a python environment. This breaks up the process, so be sure to call
            ``topo.tidy_bathymetry() after regridding with mpi."""
        )
        
        final_bathymetry = self.expt.setup_bathymetry(
            bathymetry_path=file_path,
            longitude_coordinate_name=longitude_coordinate_name,
            latitude_coordinate_name=latitude_coordinate_name,
            vertical_coordinate_name=vertical_coordinate_name,
            fill_channels=fill_channels,
            positive_down=positive_down,
            write_to_file=write_to_file,
        )
         
        self._depth = final_bathymetry.depth
            
    
    def mpi_interpolate_from_file(
        self,
        *,
        file_path,
        longitude_coordinate_name,
        latitude_coordinate_name,
        vertical_coordinate_name,
        write_directory = Path(""),
        verbose = True,
    ):
        
        if verbose:
            print(f"""
            *MANUAL REGRIDDING INSTRUCTIONS*
            
            Calling `mpi_interpolate_from_file` sets up the files necessary for regridding
            the bathymetry using mpirun and ESMF_Regrid. See below for the step-by-step instructions:
            
            1. There should be two files: `bathymetry_original.nc` and `bathymetry_unfinished.nc` located at
            {write_directory}. 
            
            2. Open a terminal and change to this directory (e.g. `cd {write_directory}`).
            
            3. Request appropriate computational resources (see example script below), and run the command:
            
            `mpirun -np NUMBER_OF_CPUS ESMF_Regrid -s bathymetry_original.nc -d bathymetry_unfinished.nc -m bilinear --src_var depth --dst_var depth --netcdf4 --src_regional --dst_regional`
            
            4. Run Topo_object.tidy_bathymetry(args) to finish processing the bathymetry. 
            
            Example PBS script using NCAR's Casper Machine: https://gist.github.com/AidanJanney/911290acaef62107f8e2d4ccef9d09be
            
            For additional details see: https://xesmf.readthedocs.io/en/latest/large_problems_on_HPC.html
            """)
            
        self.expt = self._setup_rm6_experiment(write_directory)
        
        bathymetry_output, empty_bathy = self.expt.config_bathymetry(
            bathymetry_path=file_path,
            longitude_coordinate_name=longitude_coordinate_name,
            latitude_coordinate_name=latitude_coordinate_name,
            vertical_coordinate_name=vertical_coordinate_name,
            write_to_file=True, # has to be True for mpi regridding
        )
        
        print("Configuration complete. Ready for regridding with MPI. See documentation for more details.")
            
        
    def tidy_bathymetry(
        self,
        *,
        fill_channels=False,
        positive_down=False,
        bathymetry=None,
        write_to_file=False,
    ):
        
        final_bathymetry = self.expt.tidy_bathymetry(
            fill_channels,
            positive_down,
            bathymetry=bathymetry,
            write_to_file=write_to_file)
        
        self._depth = final_bathymetry.depth
        
        print("""Regridding bathymetry complete. The Topo object now holds the bathymetry information, 
              and it can be modified and visualized using the Topo Editor.""")
        
        