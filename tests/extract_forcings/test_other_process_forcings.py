from CrocoDash.extract_forcings import (
    bgc,
    runoff as rof,
    tides,
    chlorophyll as chl,
)


def test_process_chl():
    raise NotADirectoryError(
        "Chlorophyll processing is not implemented yet. It's tricky because we need to setup the regional_mom6 experiment object first."
    )
    chl.process_chl(
        ocn_grid=self.ocn_grid,
        ocn_topo=self.ocn_topo,
        chl_processed_filepath=self.fcr["chl"].chl_processed_filepath,
        output_filepath=self.fcr["chl"].chl_output_filepath,
    )
