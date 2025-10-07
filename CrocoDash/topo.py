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
        write_to_file=False
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
        print(
            "If bathymetry setup fails, rerun this function with write_to_file = True"
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

        # Set units - to be added to rm6 through m6b
        self._depth.attrs["units"] = "meters"
