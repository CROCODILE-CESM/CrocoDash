import pytest
import numpy as np
import xarray as xr


@pytest.fixture
def get_dummy_bathymetry_data():
    latitude_extent = [2, 10]
    longitude_extent = [260, 280]
    bathymetry = np.random.random((100, 100)) * (-100)
    bathymetry = xr.DataArray(
        bathymetry,
        dims=["lat", "lon"],
        coords={
            "lat": np.linspace(latitude_extent[0] - 5, latitude_extent[1] + 5, 100),
            "lon": np.linspace(longitude_extent[0] - 5, longitude_extent[1] + 5, 100),
        },
    )
    bathymetry.name = "elevation"
    return bathymetry


@pytest.fixture(scope="session")
def dummy_tidal_data():
    nx = 100
    ny = 100
    nc = 15
    nct = 4

    # Define tidal constituents
    con_list = [
        "m2  ",
        "s2  ",
        "n2  ",
        "k2  ",
        "k1  ",
        "o1  ",
        "p1  ",
        "q1  ",
        "mm  ",
        "mf  ",
        "m4  ",
        "mn4 ",
        "ms4 ",
        "2n2 ",
        "s1  ",
    ]
    con_data = np.array([list(con) for con in con_list], dtype="S1")

    # Generate random data for the variables
    lon_z_data = np.tile(np.linspace(-180, 180, nx), (ny, 1)).T
    lat_z_data = np.tile(np.linspace(-90, 90, ny), (nx, 1))
    ha_data = np.random.rand(nc, nx, ny)
    hp_data = np.random.rand(nc, nx, ny) * 360  # Random phases between 0 and 360
    hRe_data = np.random.rand(nc, nx, ny)
    hIm_data = np.random.rand(nc, nx, ny)

    # Create the xarray dataset
    ds_h = xr.Dataset(
        {
            "con": (["nc", "nct"], con_data),
            "lon_z": (["nx", "ny"], lon_z_data),
            "lat_z": (["nx", "ny"], lat_z_data),
            "ha": (["nc", "nx", "ny"], ha_data),
            "hp": (["nc", "nx", "ny"], hp_data),
            "hRe": (["nc", "nx", "ny"], hRe_data),
            "hIm": (["nc", "nx", "ny"], hIm_data),
        },
        coords={
            "nc": np.arange(nc),
            "nct": np.arange(nct),
            "nx": np.arange(nx),
            "ny": np.arange(ny),
        },
        attrs={
            "type": "Fake OTIS tidal elevation file",
            "title": "Fake TPXO9.v1 2018 tidal elevation file",
        },
    )

    # Generate random data for the variables for u_tpxo9.v1
    lon_u_data = (
        np.random.rand(nx, ny) * 360 - 180
    )  # Random longitudes between -180 and 180
    lat_u_data = (
        np.random.rand(nx, ny) * 180 - 90
    )  # Random latitudes between -90 and 90
    lon_v_data = (
        np.random.rand(nx, ny) * 360 - 180
    )  # Random longitudes between -180 and 180
    lat_v_data = (
        np.random.rand(nx, ny) * 180 - 90
    )  # Random latitudes between -90 and 90
    Ua_data = np.random.rand(nc, nx, ny)
    ua_data = np.random.rand(nc, nx, ny)
    up_data = np.random.rand(nc, nx, ny) * 360  # Random phases between 0 and 360
    Va_data = np.random.rand(nc, nx, ny)
    va_data = np.random.rand(nc, nx, ny)
    vp_data = np.random.rand(nc, nx, ny) * 360  # Random phases between 0 and 360
    URe_data = np.random.rand(nc, nx, ny)
    UIm_data = np.random.rand(nc, nx, ny)
    VRe_data = np.random.rand(nc, nx, ny)
    VIm_data = np.random.rand(nc, nx, ny)

    # Create the xarray dataset for u_tpxo9.v1
    ds_u = xr.Dataset(
        {
            "con": (["nc", "nct"], con_data),
            "lon_u": (["nx", "ny"], lon_u_data),
            "lat_u": (["nx", "ny"], lat_u_data),
            "lon_v": (["nx", "ny"], lon_v_data),
            "lat_v": (["nx", "ny"], lat_v_data),
            "Ua": (["nc", "nx", "ny"], Ua_data),
            "ua": (["nc", "nx", "ny"], ua_data),
            "up": (["nc", "nx", "ny"], up_data),
            "Va": (["nc", "nx", "ny"], Va_data),
            "va": (["nc", "nx", "ny"], va_data),
            "vp": (["nc", "nx", "ny"], vp_data),
            "URe": (["nc", "nx", "ny"], URe_data),
            "UIm": (["nc", "nx", "ny"], UIm_data),
            "VRe": (["nc", "nx", "ny"], VRe_data),
            "VIm": (["nc", "nx", "ny"], VIm_data),
        },
        coords={
            "nc": np.arange(nc),
            "nct": np.arange(nct),
            "nx": np.arange(nx),
            "ny": np.arange(ny),
        },
        attrs={
            "type": "Fake OTIS tidal transport file",
            "title": "Fake TPXO9.v1 2018 WE/SN transports/currents file",
        },
    )

    return ds_h, ds_u

@pytest.fixture
def dummy_mom6_obc_data_factory():
    """
    Factory fixture to create dummy OBC MOM6 formatted datasets with configurable latitudes.
    """
    def _create_dummy_mom6_obc_data(lat_min=30, lat_max=35, lon_min=30, lon_max=35, segment_number = 1):
        latitude = np.linspace(lat_min, lat_max, 20)
        longitude = np.linspace(lon_min, lon_max, 20)
        time = np.arange(32)

        # Define dimensions
        time_dim = 32
        nz_u_dim = 50
        nz_v_dim = 50
        nz_salt_dim = 50
        nz_temp_dim = 50
        nz_depth_dim = 50
        nx_dim = 20
        ny_dim = 20

        # Lat/Lon ranges as arguments
        lat_range = latitude  # Adjust as needed
        lon_range = longitude  # Adjust as needed

        # Create dummy data for variables
        time = np.arange(time_dim)
        u_segment = np.full((time_dim, nz_u_dim, ny_dim, nx_dim), 1.e+20)
        v_segment = np.full((time_dim, nz_v_dim, ny_dim, nx_dim), 1.e+20)
        eta_segment = np.full((time_dim, ny_dim, nx_dim), 1.e+20)
        salt_segment = np.full((time_dim, nz_salt_dim, ny_dim, nx_dim), 1.e+20)
        temp_segment = np.full((time_dim, nz_temp_dim, ny_dim, nx_dim), 1.e+20)
        dz_salt_segment = np.full((time_dim, nz_salt_dim, ny_dim, nx_dim), 1.e+20)
        dz_temp_segment = np.full((time_dim, nz_temp_dim, ny_dim, nx_dim), 1.e+20)
        dz_u_segment = np.full((time_dim, nz_u_dim, ny_dim, nx_dim), 1.e+20)
        dz_v_segment = np.full((time_dim, nz_v_dim, ny_dim, nx_dim), 1.e+20)
        depth = np.full(nz_depth_dim, np.nan)

        # Create xarray Dataset with dynamic segment_number
        ds = xr.Dataset(
            {
                f"u_segment_{segment_number:03}": (["time", f"nz_segment_{segment_number:03}_u", "ny_segment_002", "nx_segment_002"], u_segment),
                f"v_segment_{segment_number:03}": (["time", f"nz_segment_{segment_number:03}_v", "ny_segment_002", "nx_segment_002"], v_segment),
                f"eta_segment_{segment_number:03}": (["time", "ny_segment_002", "nx_segment_002"], eta_segment),
                f"salt_segment_{segment_number:03}": (["time", f"nz_segment_{segment_number:03}_salt", "ny_segment_002", "nx_segment_002"], salt_segment),
                f"temp_segment_{segment_number:03}": (["time", f"nz_segment_{segment_number:03}_temp", "ny_segment_002", "nx_segment_002"], temp_segment),
                f"dz_salt_segment_{segment_number:03}": (["time", f"nz_salt_segment_{segment_number:03}", "ny_segment_002", "nx_segment_002"], dz_salt_segment),
                f"dz_temp_segment_{segment_number:03}": (["time", f"nz_temp_segment_{segment_number:03}", "ny_segment_002", "nx_segment_002"], dz_temp_segment),
                f"dz_u_segment_{segment_number:03}": (["time", f"nz_u_segment_{segment_number:03}", "ny_segment_002", "nx_segment_002"], dz_u_segment),
                f"dz_v_segment_{segment_number:03}": (["time", f"nz_v_segment_{segment_number:03}", "ny_segment_002", "nx_segment_002"], dz_v_segment),
                "depth": (["depth"], depth),
                "time": (["time"], time),
                "lon_segment_002": (["nx_segment_002"], lon_range),
                "lat_segment_002": (["nx_segment_002"], lat_range),
                f"nz_segment_{segment_number:03}_salt": (["nz_segment_{segment_number:03}_salt"], np.arange(nz_salt_dim)),
                f"nz_segment_{segment_number:03}_temp": (["nz_segment_{segment_number:03}_temp"], np.arange(nz_temp_dim)),
                f"nz_segment_{segment_number:03}_u": (["nz_segment_{segment_number:03}_u"], np.arange(nz_u_dim)),
                f"nz_segment_{segment_number:03}_v": (["nz_segment_{segment_number:03}_v"], np.arange(nz_v_dim)),
                "nx_segment_002": (["nx_segment_002"],np.arange(20)),
                "ny_segment_002": (["ny_segment_002"], np.arange(20)),
            },
            attrs={
                "title": "Dummy Forcing OBC Segment",
                "history": "Created using pytest fixture",
                "comment": "This is a dummy dataset for testing purposes",
            }
        )

        # Adding the _FillValue attributes dynamically based on segment_number
        ds.attrs["_FillValue"] = 1.e+20
        return ds

    return _create_dummy_mom6_obc_data
@pytest.fixture
def dummy_forcing_factory():
    """Factory fixture to create dummy forcing NetCDF datasets with configurable latitudes."""

    def _create_dummy_forcing_dataset(lat_min=30, lat_max=35, lon_min=30, lon_max=35):
        latitude = np.linspace(lat_min, lat_max, 20)
        longitude = np.linspace(lon_min, lon_max, 20)
        depth = np.array(
            [0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000], dtype=np.float64
        )
        time = np.arange(32)

        data = {
            "so": (
                ("time", "depth", "latitude", "longitude"),
                np.random.rand(32, 10, 20, 20).astype(np.float64),
            ),
            "thetao": (
                ("time", "depth", "latitude", "longitude"),
                np.random.rand(32, 10, 20, 20).astype(np.float64),
            ),
            "uo": (
                ("time", "depth", "latitude", "longitude"),
                np.random.rand(32, 10, 20, 20).astype(np.float64),
            ),
            "vo": (
                ("time", "depth", "latitude", "longitude"),
                np.random.rand(32, 10, 20, 20).astype(np.float64),
            ),
            "zos": (
                ("time", "latitude", "longitude"),
                np.random.rand(32, 20, 20).astype(np.float64),
            ),
        }

        ds = xr.Dataset(
            data,
            coords={
                "depth": depth,
                "latitude": latitude,
                "longitude": longitude,
                "time": time,
            },
        )
        return ds

    return _create_dummy_forcing_dataset
