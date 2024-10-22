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
    Create a regional grids for MOM6, designed to work for the CROCODILE regional MOM6 workflow w/ regional_mom6
    """

    @property
    def hgrid(self):
        try:
            return xr.open_dataset(self._hgrid_path)
        except:
            return "Unable to find hgrid file"

    @hgrid.setter
    def hgrid(self, value):
        self._hgrid_path = os.path.join(self.temp_storage, "hgrid.nc")
        export_dataset(value, self._hgrid_path)

    @property
    def topo(self):
        try:
            return xr.open_dataset(self._topo_path)
        except:
            return "Unable to find topo file"

    @topo.setter
    def topo(self, value):
        self._topo_path = os.path.join(self.temp_storage, "topo.nc")
        export_dataset(value, self._topo_path)

    @property
    def vgrid(self):
        try:
            return xr.open_dataset(self._vgrid_path)
        except:
            return "Unable to find vgrid file"

    @vgrid.setter
    def vgrid(self, value):
        self._vgrid_path = os.path.join(self.temp_storage, "vgrid.nc")
        export_dataset(value, self._vgrid_path)

    def __init__(
        self,
        latitude_extent=None,
        longitude_extent=None,
        resolution=None,
        delete_temp_storage=True,
    ):
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
        if self.delete_temp_storage:
            try:
                shutil.rmtree(self.temp_storage)
            except:
                gridgen_logger.info(
                    "Error cleaning up CRR grid_gen temp storage directory."
                )

    def subset_global_hgrid(
        self,
        longitude_extent=None,
        latitude_extent=None,
        path="/glade/work/fredc/cesm/grid/MOM6/tx1_12v1/gridgen/ocean_hgrid_trimmed.nc",
    ):
        """
        Read in global supergrid, find closest points to the extent, and subset the supergrid to the extent.
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

    def create_rectangular_hgrid(self, longitude_extent, latitude_extent, resolution):
        """
        Set up a horizontal grid based on user's specification of the domain.
        The default behaviour generates a grid evenly spaced both in longitude
        and in latitude.

        The latitudinal resolution is scaled with the cosine of the central
        latitude of the domain, i.e., ``Δlats = cos(lats_central) * Δlons``, where ``Δlons``
        is the longitudinal spacing. This way, for a sufficiently small domain,
        the linear distances between grid points are nearly identical:
        ``Δx = R * cos(lats) * Δlons`` and ``Δy = R * Δlats = R * cos(lats_central) * Δlons``
        (here ``R`` is Earth's radius and ``lats``, ``lats_central``, ``Δlons``, and ``Δlats``
        are all expressed in radians).
        That is, if the domain is small enough that so that ``cos(lats_North_Side)``
        is not much different from ``cos(lats_South_Side)``, then ``Δx`` and ``Δy``
        are similar.

        Note:
            The intention is for the horizontal grid (``hgrid``) generation to be flexible.
            For now, there is only one implemented horizontal grid included in the package,
            but you can customise it by simply overwriting the ``hgrid.nc`` file in the
            ``mom_run_dir`` directory after initialising an ``experiment``. To preserve the
            metadata, it might be easiest to read the file in, then modify the fields before
            re-saving.
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
        Generates a vertical grid based on the ``number_vertical_layers``, the ratio
        of largest to smallest layer thickness (``layer_thickness_ratio``) and the
        total ``depth`` parameters.
        (All these parameters are specified at the class level.)
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
            I[0] // 2,
            J[0] // 2,
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
        """ """
        expt = rm6.experiment.create_empty(
            mom_input_dir=input_dir, minimum_depth=minimum_depth
        )
        expt.tidy_bathymetry(fill_channels=fill_channels, positive_down=positive_down)

    def export_files(self, output_folder):
        """
        Export all files from the temp_storage directory to the output_folder.

        Parameters:
        output_folder (str): Path to the output directory where files will be copied.
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
