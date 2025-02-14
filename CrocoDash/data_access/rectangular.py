"""
This script functions are directly called from CrocoDash.case to get the rectangular boundary conditions from segment calls in specific data product scripts
"""

def get_rectangular_segment_info(hgrid):
    """
    This function finds the required segment queries from the hgrid and calls the functions
    """
    east_result = {
        "lon_min":float(hgrid.x.isel(nxp=-1).min()),
        "lon_max":   float(hgrid.x.isel(nxp=-1).max()),
        "lat_min":float(hgrid.y.isel(nxp=-1).min()),
        "lat_max":float(hgrid.y.isel(nxp=-1).max()),
    }
    west_result = {
        "lon_min":float(hgrid.x.isel(nxp=0).min()),
        "lon_max":   float(hgrid.x.isel(nxp=0).max()),
        "lat_min":float(hgrid.y.isel(nxp=0).min()),
        "lat_max":float(hgrid.y.isel(nxp=0).max()),
    }
    south_result = {
        "lon_min":float(hgrid.x.isel(nyp=0).min()),
        "lon_max":   float(hgrid.x.isel(nyp=0).max()),
        "lat_min":float(hgrid.y.isel(nyp=0).min()),
        "lat_max":float(hgrid.y.isel(nyp=0).max()),
    }
    north_result = {
        "lon_min":float(hgrid.x.isel(nyp=-1).min()),
        "lon_max":   float(hgrid.x.isel(nyp=-1).max()),
        "lat_min":float(hgrid.y.isel(nyp=-1).min()),
        "lat_max":float(hgrid.y.isel(nyp=-1).max()),
    }
    return {
        "east_result":east_result,
        "west_result":west_result,
        "north_result":north_result,
        "south_result":south_result
    }

def get_rectangular_boundary_conditions(dates, hgrid, data_access_function, other_function_params = {}):
    """
    This function finds the required segment queries from the hgrid and calls the functions
    """
    results = {}
    results_info = get_rectangular_segment_info(hgrid)
    for key in results_info.keys():
        results[key] = data_access_function(
        dates = dates,
        lon_min = results_info["lon_min"],
        lon_max =    results_info["lon_max"],
        lat_min = results_info["lat_min"],
        lat_max = results_info["lat_max"],
        **other_function_params
    )

    return results