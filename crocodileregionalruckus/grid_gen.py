import regional_mom6.regional_mom6 as rm6


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

    def generate_rectangle_grid(self):
        return

