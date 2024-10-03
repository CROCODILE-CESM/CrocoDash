import xarray as xr

class GridGen:

    """
    Create a regional grids for MOM6, designed to work for the CROCODILE regional MOM6 workflow w/ regional_mom6
    """

    def __init__(self,latitude_extent, longitude_extent):
        self.latitude_extent = latitude_extent
        self.longitude_extent = longitude_extent
        self.grid_ds = None

    def subset_global_grid(self):
        return
    
    def generate_expt_object(self):
        return

    def generate_rectangle_grid(self, read_existing_grids = False):
        if read_existing_grids:
            try:
                self.hgrid = xr.open_dataset(self.mom_input_dir / "hgrid.nc")
                self.vgrid = xr.open_dataset(self.mom_input_dir / "vcoord.nc")
            except:
                print(
                    "Error while reading in existing grids!\n\n"
                    + f"Make sure `hgrid.nc` and `vcoord.nc` exists in {self.mom_input_dir} directory."
                )
                raise ValueError
        else:
            self.hgrid = self._make_hgrid()
            self.vgrid = self._make_vgrid()

