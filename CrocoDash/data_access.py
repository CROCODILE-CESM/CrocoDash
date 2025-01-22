"""
Data Access Module -> Query Data Sources like GLORYS & GEBCO
"""
import xarray as xr
import glob
import os
import copernicusmarine

def get_glorys_data_from_rda(dates: list,lat_min, lat_max, lon_min,lon_max) -> xr.Dataset:
    """
    Gather GLORYS Data on Derecho Computers from the campaign storage and return the dataset sliced to the llc and urc coordinates at the specific dates 
    """

    # Set 
    drop_var_lst = ['mlotst','bottomT','sithick','siconc','usi','vsi']
    ds_in_path = '/glade/campaign/cgd/oce/projects/CROCODILE/glorys012/GLOBAL/'
    ds_in_files = []
    date_strings = [date.strftime('%Y%m%d') for date in dates]
    for date in date_strings:
        pattern = os.path.join(ds_in_path, "**",f'*{date}*.nc')
        ds_in_files.extend(glob.glob(pattern, recursive=True))
    ds_in_files = sorted(ds_in_files)
    dataset = xr.open_mfdataset(ds_in_files,decode_times=False).drop_vars(drop_var_lst).sel(latitude=slice(lat_min,lat_max),longitude=slice(lon_min,lon_max))

    return dataset

def get_glorys_data_from_cds_api(dates: tuple, lat_min, lat_max, lon_min, lon_max) -> xr.Dataset:
    """
    Using the copernucismarine api, query GLORYS data
    """
    ds = copernicusmarine.open_dataset(
        dataset_id = 'cmems_mod_glo_phy_my_0.083deg_P1D-m',
            minimum_longitude = lon_min,
    maximum_longitude = lon_max,
    minimum_latitude = lat_min,
    maximum_latitude = lat_max,
        start_datetime = dates[0],
    end_datetime = dates[1],
    variables=["uo","vo","thetao","so","zos"],
    )
    return ds