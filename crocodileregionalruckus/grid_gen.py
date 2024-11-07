"""
This module (grid_gen) implements the GridGen class, three helper functions (spherical2cartesian, create_tree, find_nearest) useful in subsetting a grid, and contains a logger called "grid_gen_logger"
"""

from .utils import setup_logger

gridgen_logger = setup_logger(__name__)
import xarray as xr
import numpy as np
from .utils import *
import xesmf as xe
from scipy.spatial import cKDTree
from scipy.ndimage import label
import shutil
from .rm6 import regional_mom6 as rm6
import os
from crocodileregionalruckus.utils import export_dataset
from pathlib import Path


class GridGen:
    """
    This class is the grid generation class for the Crocodile Regional Ruckus. It stores all variables and functions used to generate hgrids, vgrids, and topography files for regional MOM6 experiments.
    Apart from native grid generation, it wraps a couple of regional-mom6 functions to keep all the grid generation code in one place.

    This class currently only generates rectanglular-ish grids.

    Variables:

    1. ``hgrid`` : A property variable that stores the hgrid dataset
    2. ``topo`` : A property variable that stores the topography dataset
    3. ``vgrid`` : A property variable that stores the vgrid dataset
    4. ``latitude_extent`` : Extents of the rectangular grid in latitude
    5. ``longitude_extent`` : Extents of the rectangular grid in longitude
    6. ``resolution`` : Resolution of the rectangular grid (for use in regional-mom6 _create_hgrid)
    7. ``temp_storage`` : Temporary storage directory on all the datasets to offload heavy memory items

    Functions:

    1. ``__init__`` : Initializes the GridGen object with no required parameters
    2. ``__del__`` : Deletes the temp_storage directory to save memory
    3. ``subset_global_hgrid`` : Subsets a global hgrid (default on glade) to the extents specified (rectangular)
    4. ``subset_global_topo`` : Subsets a global topo (default on glade) to the extents specified (rectangular)
    5. ``verify_and_modify_read_vgrid`` : Verifies the vertical grid of the dataset. If only a thickness is given, it generates the midpoint and interface levels for regridding of the boundary conditions
    6. ``create_rectangular_hgrid`` : Wraps regional-mom6 _make_hgrid to create a rectangular hgrid
    7. ``create_vgrid``: Wraps regional-mom6 _make_vgrid to create a vertical grid
    8. ``mask_disconnected_ocean_areas``: Masks out disconnected ocean areas in the topography file. For example, if we have a rectangle over Central America for Gulf Stream research, we likely only want the Gulf of Mexico, so we mask out the Pacific.
    9. ``setup_bathymetry``: Sets up the bathymetry file for the regional mom6 experiment. Wraps regional-mom6 setup_bathymetry
    10. ``tidy_bathymetry``: Tidies up the bathymetry file from setup_bathymetry for the regional mom6 experiment. Wraps regional-mom6 tidy_bathymetry
    11. ``export_files``: Exports all files from the temp_storage directory to the output_folder
    """

    @property
    def hgrid(self):
        """
        Gets the Hgrid as a xr.Dataset
        """
        try:
            return xr.open_dataset(self._hgrid_path)
        except:
            return "Unable to find hgrid file"

    @hgrid.setter
    def hgrid(self, value):
        """
        Sets the Hgrid given a xr.Dataset
        """
        self._hgrid_path = os.path.join(self.temp_storage, "hgrid.nc")
        export_dataset(value, self._hgrid_path)

    @property
    def topo(self):
        """
        Gets the Topo as a xr.Dataset
        """
        try:
            return xr.open_dataset(self._topo_path)
        except:
            return "Unable to find topo file"

    @topo.setter
    def topo(self, value):
        """
        Sets the Topo given a xr.Dataset"""
        self._topo_path = os.path.join(self.temp_storage, "topo.nc")
        export_dataset(value, self._topo_path)

    @property
    def vgrid(self):
        """
        Gets the Vgrid as a xr.Dataset
        """
        try:
            return xr.open_dataset(self._vgrid_path)
        except:
            return "Unable to find vgrid file"

    @vgrid.setter
    def vgrid(self, value):
        """
        Sets the Vgrid given a xr.Dataset"""
        self._vgrid_path = os.path.join(self.temp_storage, "vgrid.nc")
        export_dataset(value, self._vgrid_path)

    def __init__(
        self,
        latitude_extent=None,
        longitude_extent=None,
        resolution=None,
        delete_temp_storage=True,
    ):
        """
        This init function takes in any arguments we might need for grid generation for easy storage. They aren't used in any of the functions as they much be decalred in the function arguments explicitly.
        We can also declare if we want the temp_storage directory deleted after the object is deleted.

        Parameters
        ----------
        latitude_extent : list
            Latitude extent of the grid
        longitude_extent : list
            Longitude extent of the grid
        resolution : float
            Resolution of the grid
        delete_temp_storage : bool
            Whether to delete the temporary storage directory after the object is deleted
        """
        self.latitude_extent = latitude_extent
        self.longitude_extent = longitude_extent
        self.resolution = resolution
        self._hgrid_path = None
        self._vgrid_path = None
        self._topo_path = None
        self.delete_temp_storage = delete_temp_storage
        # Create a temporary storage directory to offload heavy memory items.
        self.temp_storage = ".crr_gg_temp"
        os.makedirs(self.temp_storage, exist_ok=True)

    def __del__(self):
        """
        This function cleans up our object. If we declare delete_temp_storage as True in the __init__ (which is default), we delete the temp_storage directory after the object is deleted.
        """
        if self.delete_temp_storage:
            try:
                shutil.rmtree(self.temp_storage)
            except:
                gridgen_logger.info(
                    "Couldn't clean up CRR grid_gen temp storage directory."
                )

    def subset_global_hgrid(
        self,
        longitude_extent=None,
        latitude_extent=None,
        path="/glade/work/fredc/cesm/grid/MOM6/tx1_12v1/gridgen/ocean_hgrid_trimmed.nc",
    ):
        """
        This function reads in a global supergrid (path), finds the closest points to the extents, and subsets the supergrid to that extent.

        Parameters
        ----------
        longitude_extent : list
            Longitude extent of the grid
        latitude_extent : list
            Latitude extent of the grid
        path : str
            Path to the global supergrid file
        Returns
        -------
        ds_nwa : xarray.Dataset
            The subsetted supergrid dataset
        """

        try:
            with xr.open_dataset(path, chunks={"nx": 1000, "ny": 1000}) as dsg:
                kdtree = create_tree(dsg.x, dsg.y)
                I_llc, J_llc = find_nearest(
                    dsg.x,
                    dsg.y,
                    min(longitude_extent),
                    min(latitude_extent),
                    tree=kdtree,
                )
                I_urc, J_urc = find_nearest(
                    dsg.x,
                    dsg.y,
                    max(longitude_extent),
                    max(latitude_extent),
                    tree=kdtree,
                )
                # Ensure I_llc and J_llc are even
                if I_llc[0] % 2 != 0:
                    I_llc[0] += 1
                if J_llc[0] % 2 != 0:
                    J_llc[0] += 1

                # Ensure I_urc and J_urc are even
                if I_urc[0] % 2 != 0:
                    I_urc[0] += 1
                if J_urc[0] % 2 != 0:
                    J_urc[0] += 1
                ds_nwa = dsg.isel(nx=slice(I_llc[0], I_urc[0])).isel(
                    ny=slice(J_llc[0], J_urc[0])
                )
                ds_nwa = ds_nwa.isel(nxp=slice(I_llc[0], I_urc[0] + 1)).isel(
                    nyp=slice(J_llc[0], J_urc[0] + 1)
                )
                return ds_nwa
        except:
            raise FileNotFoundError(
                "Global Supergrid not found. We looked here {}. I would instead use the create_rectangular_hgrid method to create a new grid, or pass in a path with 'path='".format(
                    path
                )
            )

    def subset_global_topo(
        self,
        longitude_extent,
        latitude_extent,
        hgrid_path="/glade/work/fredc/cesm/grid/MOM6/tx1_12v1/gridgen/ocean_hgrid_trimmed.nc",
        topo_path="/glade/work/bryan/MOM6-data-files/Topography/tx1_12v1/topo.sub25.tx1_12v1.srtm.edit1.SmL1.0_C1.0.nc",
    ):
        """
        This function reads in a global supergrid and companion topo file (hgrid_path, topo), finds the closest points to the extents in the hgrid, and subsets the topo file to that extent.

        Parameters
        ----------
        longitude_extent : list
            Longitude extent of the grid
        latitude_extent : list
            Latitude extent of the grid
        hgrid_path : str
            Path to the global supergrid file
        topo_path : str
            Path to the global topo file
        Returns
        -------
        topo : xarray.Dataset
            The subsetted topo dataset
        """

        try:
            with xr.open_dataset(hgrid_path, chunks={"nx": 1000, "ny": 1000}) as dsg:
                tree = create_tree(dsg.x, dsg.y)
                I_llc, J_llc = find_nearest(
                    dsg.x, dsg.y, min(longitude_extent), min(latitude_extent), tree=tree
                )
                I_urc, J_urc = find_nearest(
                    dsg.x, dsg.y, max(longitude_extent), max(latitude_extent), tree=tree
                )
                # Ensure I_llc and J_llc are even
                if I_llc[0] % 2 != 0:
                    I_llc[0] += 1
                if J_llc[0] % 2 != 0:
                    J_llc[0] += 1

                # Ensure I_urc and J_urc are even
                if I_urc[0] % 2 != 0:
                    I_urc[0] += 1
                if J_urc[0] % 2 != 0:
                    J_urc[0] += 1
        except:
            raise FileNotFoundError(
                "Global Supergrid not found. We looked here {}. I would instead use the create_rectangular_hgrid method to create a new grid, or pass in a path with 'path='".format(
                    hgrid_path
                )
            )
        try:
            with xr.open_dataset(
                topo_path, chunks={"nx": 1000, "ny": 1000}
            ) as dsg_topo:
                I_llc, J_llc = I_llc[0], J_llc[0]
                I_urc, J_urc = I_urc[0], J_urc[0]
                i1 = I_llc // 2
                j1 = J_llc // 2
                nx = (I_urc - I_llc) // 2
                ny = (J_urc - J_llc) // 2
                i2 = i1 + nx
                j2 = j1 + ny
                topo = (
                    dsg_topo["D_interp_L1.0_C1.0"]
                    .isel(lonh=slice(i1, i2))
                    .isel(lath=slice(j1, j2))
                )
                self.topo = topo.to_dataset(name="depth")
        except:
            raise FileNotFoundError(
                "Global Topo not found. We looked here {}. I would instead use the create_rectangular_hgrid method to create a new grid, or pass in a path with 'path='".format(
                    topo_path
                )
            )

        # Mask and Topo files are on the model grid, which is a division of 2 of the supergrid in each dimension

        return self.topo

    def verify_and_modify_read_vgrid(self, path_to_ds, thickness_name="dz"):
        """
        This function verifies the vertical grid of the dataset. We need a midpoint (zl) and interface level (zi). We need the midpoint of the thickness to regrid the initial condition, and zi is just so we don't have to change MOM_input.
        This function is able to check if we have those things, and if not, add them based on a thickness variable. If no thickness variable is given, and we don'thave zl and zi, this function fails.

        Parameters
        ----------
        path_to_ds : str
            Path to the dataset.
        thickness_name : str
            Name of the thickness variable in the dataset. Default is dz.
        Returns
        -------
        dataset: str
            The dataset with the adjusted (or not) vertical grid.
        """
        need_to_add_zl = False
        vgrid = xr.open_dataset(path_to_ds)
        if "zl" not in vgrid:
            gridgen_logger.info(
                f"Dataset {path_to_ds} does not contain zl. We need it to regrid the initial condition! I can add it based on dz!"
            )
            need_to_add_zl = True
        else:
            gridgen_logger.info(f"Dataset {path_to_ds} contains zl.")
        if "zi" not in vgrid:
            gridgen_logger.warning(
                f"Dataset {path_to_ds} does not contain zi. Make sure to change ALE_COORDINATE_CONFIG to what your vertical coordinate is called..."
            )

        if need_to_add_zl:
            if thickness_name in vgrid:
                dz = vgrid[thickness_name].values
                zi = dz.cumsum()
                zi = np.insert(zi, 0, 0.0)
                vgrid["zi"] = xr.DataArray(
                    zi,
                    dims=["zi"],
                    attrs={"long_name": "Layer interfaces", "units": "m"},
                )
                gridgen_logger.info(
                    f"Added zi to vgrid. Make sure to save this before reading into regional mom!"
                )
                zl = dz.cumsum() - dz / 2
                vgrid["zl"] = xr.DataArray(
                    zl,
                    dims=["zl"],
                    attrs={"long_name": "Layer midpoints", "units": "m"},
                )
                gridgen_logger.info(
                    f"Added zl to vgrid. Make sure to save this before reading into regional mom!"
                )
            else:
                raise ValueError(
                    f"Dataset does not contain {thickness_name}. Cannot add zl without {thickness_name} in this code, which means regional mom6 won't be able to regrid the initial condition. Try adding it yourself"
                )
        return vgrid

    def create_rectangular_hgrid(self, longitude_extent, latitude_extent, resolution):
        """
        This function wraps regional-mom6 _make_hgrid to create a rectangular hgrid

        Parameters
        ----------
        longitude_extent : list
            Longitude extent of the grid
        latitude_extent : list
            Latitude extent of the grid
        resolution : float
            Resolution of the grid
        Returns
        -------
        hgrid : xarray.Dataset
            The hgrid dataset
        """
        expt = rm6.experiment.create_empty(
            longitude_extent=longitude_extent,
            latitude_extent=latitude_extent,
            resolution=resolution,
            mom_input_dir=Path(self.temp_storage),
        )

        hgrid = expt._make_hgrid()
        self.hgrid = hgrid
        return hgrid

    def create_vgrid(
        self, number_vertical_layers, layer_thickness_ratio, depth, minimum_depth
    ):
        """
        Wraps regional-mom6 _make_vgrid to create a vertical grid.

        Parameters
        ----------
        number_vertical_layers : int
            Number of vertical layers
        layer_thickness_ratio : float
            Ratio of the thickness of the layers
        depth : float
            Depth of the ocean
        minimum_depth : float
            Minimum depth of the ocean
        Returns
        -------
        vcoord : xarray.Dataset
            The vgrid dataset
        """
        expt = rm6.experiment.create_empty(
            number_vertical_layers=number_vertical_layers,
            layer_thickness_ratio=layer_thickness_ratio,
            depth=depth,
            minimum_depth=minimum_depth,
            mom_input_dir=Path(self.temp_storage),
        )
        vcoord = expt._make_vgrid()

        self.vgrid = vcoord
        return vcoord

    def mask_disconnected_ocean_areas(
        self, hgrid, name_x_dim, name_y_dim, topo, lat_pt, lon_pt
    ):
        """
        This function masks areas of the topo that are not connected to lat_pt, lon_pt. This is useful for regional studies where we only want to study a specific area of the ocean, like the Atlantic, and not the Pacific Ocean.

        You use it by specifying a point in the ocean that you want to study, and it will mask out all the ocean areas that are not connected to that point. This is done by finding the connected ocean segments and isolating the segment that contains the chosen point.

        Parameters
        ----------
        hgrid : xarray.Dataset
            Horizontal grid dataset. Used to convert from lat/lon to i/j.
        name_x_dim : str
            Name of the x dimension in the horizontal grid dataset.
        name_y_dim : str
            Name of the y dimension in the horizontal grid dataset.
        topo : xarray.DataArray
            Topography data array. The item we mask, used to mask out disconnected ocean areas, where 0 indicates Land
        lat_pt, lon_pt
            Coordinates of the point to use as the starting point for the mask.

        Returns
        -------
        topo : xarray.Dataset
            The masked topography dataset
        """

        extra_dim_name = "ntiles"
        has_extra_dim = "ntiles" in topo.dims

        # Squeeze out the 'extra' dimension if it exists and has size 1
        if has_extra_dim and topo.sizes[extra_dim_name] == 1:
            topo = topo.squeeze(extra_dim_name)
        # Get Ocean Mask
        ocean_mask = xr.where((topo != 0) & (~np.isnan(topo)), 1, 0)

        # Find index of the chosen point
        I, J = find_nearest(hgrid[name_x_dim], hgrid[name_y_dim], lon_pt, lat_pt)
        nx, ny = (
            (I[0] // 2) - 1,  # -1 so we don't hit a boundary
            (J[0] // 2) - 1,
        )  # Divide by 2 to get the index on the topo grid, not the supergrid

        # Get connected ocean segments
        res, num_features = label(ocean_mask)

        # Isolate the segment that contains the chosen point, and remask ocean mask
        ocean_mask_changed = xr.where(res == res[ny, nx], 1, 0)

        # Convert ocean_mask to xr.DataArray
        xr_ocean_mask_changed = xr.DataArray(
            ocean_mask_changed, coords=ocean_mask.coords, dims=ocean_mask.dims
        )

        # Make all the newly masked ocean points into land points in the topo file
        topo = xr.where(xr_ocean_mask_changed == 0, 0, topo)
        if has_extra_dim:
            topo = topo.expand_dims(extra_dim_name)
        self.topo = topo.to_dataset(name="depth")
        return self.topo

    def setup_bathymetry(
        self,
        hgrid,
        longitude_extent,
        latitude_extent,
        input_dir,
        minimum_depth,
        bathymetry_path,
        longitude_coordinate_name="lon",
        latitude_coordinate_name="lat",
        vertical_coordinate_name="elevation",
        fill_channels=False,
        positive_down=False,
    ):
        """
        This function wraps regional-mom6 setup_bathymetry to set up the bathymetry file for the regional mom6 experiment.

        Parameters
        ----------
        hgrid : xarray.Dataset
            Horizontal grid dataset
        longitude_extent : list
            Longitude extent of the grid
        latitude_extent : list
            Latitude extent of the grid
        input_dir : str
            Path to the input directory (where to put the bathymetry file)
        minimum_depth : float
            Minimum depth of the ocean
        bathymetry_path : str
            Path to the global/gebco bathymetry file
        longitude_coordinate_name: str
            Name of the longitude coordinate in the bathymetry file, default is lon
        latitude_coordinate_name: str
            Name of the latitude coordinate in the bathymetry file, default is lat
        vertical_coordinate_name: str
            Name of the vertical coordinate in the bathymetry file, default is elevation
        fill_channels : bool
            Whether to fill channels in the bathymetry file, default is False
        positive_down : bool
            Whether the vertical coordinate is positive down, default is False

        Returns
        -------
        topo : xarray.Dataset
            The bathymetry dataset

        """
        expt = rm6.experiment.create_empty()
        expt.hgrid = hgrid
        expt.longitude_extent = longitude_extent
        expt.latitude_extent = latitude_extent
        expt.mom_input_dir = input_dir
        expt.minimum_depth = minimum_depth
        expt.setup_bathymetry(
            bathymetry_path=bathymetry_path,
            longitude_coordinate_name=longitude_coordinate_name,
            latitude_coordinate_name=latitude_coordinate_name,
            vertical_coordinate_name=vertical_coordinate_name,
            fill_channels=fill_channels,
            positive_down=positive_down,
        )
        expt.bathymetry = xr.load_dataset(expt.mom_input_dir / "bathymetry.nc")
        self.topo = expt.bathymetry
        return self.topo

    def tidy_bathymetry(
        self, input_dir, minimum_depth, fill_channels=False, positive_down=False
    ):
        """
        This function wraps regional-mom6 tidy_bathymetry to tidy up the bathymetry file from setup_bathymetry for the regional mom6 experiment.

        Parameters
        ----------
        input_dir : str
            Path to the input directory (where the bathymetry file is)
        minimum_depth : float
            Minimum depth of the ocean
        fill_channels : bool
            Whether to fill channels in the bathymetry file, default is False
        positive_down : bool
            Whether the vertical coordinate is positive down, default is False

        Returns
        -------
        None
            See your input_dir for the correct file (bathymetry.nc) from bathymetry_unfinished.nc
        """
        expt = rm6.experiment.create_empty(
            mom_input_dir=input_dir, minimum_depth=minimum_depth
        )
        expt.tidy_bathymetry(fill_channels=fill_channels, positive_down=positive_down)

    def export_files(self, output_folder):
        """
        Export all files from the temp_storage directory to the output_folder.

        Parameters
        ----------
        output_folder (str): Path to the output directory where files will be copied.
        Returns
        -------
        None
            All files have been exported to output_folder
        """
        input_dir = Path(self.temp_storage)
        output_dir = Path(output_folder)

        if not output_dir.exists():
            os.makedirs(output_dir)

        for item in input_dir.iterdir():
            if item.is_file():
                shutil.copy(item, output_dir / item.name)
            elif item.is_dir():
                shutil.copytree(item, output_dir / item.name, dirs_exist_ok=True)

        gridgen_logger.info(f"All files have been exported to {output_folder}")


def spherical2cartesian(lon, lat):
    """
    Convert spherical coordinates to cartesian coordinates
    """
    R_earth = 6378136  # meters
    lonr = np.deg2rad(lon)
    latr = np.deg2rad(lat)
    x = R_earth * np.cos(latr) * np.cos(lonr)
    y = R_earth * np.cos(latr) * np.sin(lonr)
    z = R_earth * np.sin(latr)
    return x, y, z


def create_tree(lon, lat):
    """
    Create a K-d tree from the spherical coordinates, which is good for spatial queries, like nearest neighbor search
    """
    # Convert spherical coordinates to cartesian coordinates
    x, y, z = spherical2cartesian(lon, lat)

    # Stack - flatten the cartesian coordinates in 1D arrays
    x_stack = x.stack(points=x.dims).values
    y_stack = y.stack(points=y.dims).values
    z_stack = z.stack(points=z.dims).values

    # Construct KD-tree
    tree = cKDTree(np.column_stack((x_stack, y_stack, z_stack)))

    # Return tree
    return tree


def find_nearest(lon, lat, lon_pt, lat_pt, tree=None):
    """
    Find the nearest point to lon_pt, lat_pt in the grid defined by lon, lat
    """
    # Create a tree from the grid
    if tree is None:
        tree = create_tree(lon, lat)

    # Get Cartesian coordinates of the point of interest
    xp, yp, zp = spherical2cartesian(lon_pt, lat_pt)

    # Find nearest index
    _, idx = tree.query(np.column_stack((xp, yp, zp)))

    # idx = np.unique(idx) # Remove duplicates

    # Format and return the index
    idx = np.unravel_index(idx, lon.shape)
    Iidx = idx[1]
    Jidx = idx[0]
    return Iidx, Jidx
