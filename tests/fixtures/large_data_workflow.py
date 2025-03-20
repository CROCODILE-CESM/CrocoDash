import pytest

@pytest.fixture
def generate_piecewise_raw_data(tmp_path,dummy_forcing_factory):
    ds = dummy_forcing_factory(
        0,
       10,
        0,
        10,
    )
    ds.to_netcdf(tmp_path/ "glorys" / "east_unprocessed.nc")
    ds.to_netcdf(tmp_path/ "glorys" / "west_unprocessed.nc")
    ds.to_netcdf(tmp_path/ "glorys" / "north_unprocessed.nc")
    ds.to_netcdf(tmp_path/ "glorys" / "south_unprocessed.nc")

    return 