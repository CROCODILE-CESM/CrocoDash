from regional_mom6 import *

def process_tides(self):
    raise NotADirectoryError("Tide processing is not implemented yet. It's tricky because we need to setup the regional_mom6 experiment object first.")
    self.expt.setup_boundary_tides(
        tpxo_elevation_filepath=self.fcr["tides"].tpxo_elevation_filepath,
        tpxo_velocity_filepath=self.fcr["tides"].tpxo_velocity_filepath,
        tidal_constituents=self.fcr["tides"].tidal_constituents,
    )