import xarray as xr

from mom6_bathy.topo import Topo as mom6_bathy_Topo
import regional_mom6 as rmom6
from pathlib import Path


class Topo(mom6_bathy_Topo):

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
    ):

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
        if write_to_file:
            expt.mom_input_dir = Path("")
        print(""
            """If bathymetry setup fails, restart the kernel or rerun the script.
            Call Topo_object.manual_interpolate_from_file() instead.
            Follow the given instructions for using mpirun and ESMF_Regrid outside of a python environment."""
        )
        
        self._depth = expt.setup_bathymetry(
            bathymetry_path=file_path,
            longitude_coordinate_name=longitude_coordinate_name,
            latitude_coordinate_name=latitude_coordinate_name,
            vertical_coordinate_name=vertical_coordinate_name,
            fill_channels=fill_channels,
            positive_down=positive_down,
            write_to_file=write_to_file,
        ).depth
            
    
    def manual_interpolate_from_file(
        self,
        *,
        file_path,
        longitude_coordinate_name,
        latitude_coordinate_name,
        vertical_coordinate_name,
        intermediate_directory = Path("")
    ):
        print(
            """Using manual regridding because argument because the domain/topo is too large."""
        )
        
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
        
        ## We have to write to file for the manual interpolation
        expt.mom_input_dir = intermediate_directory
        
        expt.setup_bathymetry(
            bathymetry_path=file_path,
            longitude_coordinate_name=longitude_coordinate_name,
            latitude_coordinate_name=latitude_coordinate_name,
            vertical_coordinate_name=vertical_coordinate_name,
            write_to_file=True, # have to write to file for manual interpolation
            manual_ESMF = True,
        )
        
        # Save experiment as an attribute of the current Topo object to abstract Regional Mom 6 calls from user
        self.experiment = expt  
        
        print(f"""
        *MANUAL REGRIDDING INSTRUCTIONS*
        
        Calling `manual_interpolate_from_file` has set up the necessary files to manually interpolate
        the bathymetry using mpirun and ESMF_Regrid. See below for the step-by-step instructions:
        
        1. There should be two files: `bathymetry_original.nc` and `bathymetry_unfinished.nc` located at
        {intermediate_directory}. 
        
        2. Open a terminal and change to this directory (e.g. `cd {intermediate_directory}`).
        
        3. Request appropriate computational resources (see example script below), and run the command:
        
        `mpirun -np NUMBER_OF_CPUS ESMF_Regrid -s bathymetry_original.nc -d bathymetry_unfinished.nc -m bilinear --src_var depth --dst_var depth --netcdf4 --src_regional --dst_regional`
        
        4. Run Topo_object.tidy_bathymetry(args) to finish processing the bathymetry. 
        
        Example PBS script using NCAR's Casper Machine: https://gist.github.com/AidanJanney/911290acaef62107f8e2d4ccef9d09be
        
        For additional details see: https://xesmf.readthedocs.io/en/latest/large_problems_on_HPC.html
        """)
        
    def tidy_bathymetry(
        self,
        *,
        fill_channels=False,
        positive_down=False,
        write_to_file=False,
        override_bathymetry_path=None,
    ):
        if override_bathymetry_path is not None:
            bathymetry = xr.open_dataset(override_bathymetry_path)
        else:
            bathymetry = None
            
        tidy_bathy = self.experiment.tidy_bathymetry(
            fill_channels,
            positive_down,
            bathymetry=bathymetry,
            write_to_file=write_to_file)
        
        self._depth = tidy_bathy.depth
        
        