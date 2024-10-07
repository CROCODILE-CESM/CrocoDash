import xarray as xr
import numpy as np
from .utils import *
from scipy.ndimage import binary_fill_holes
import xesmf as xe
from scipy.spatial import cKDTree


class GridGen:
    """
    Create a regional grids for MOM6, designed to work for the CROCODILE regional MOM6 workflow w/ regional_mom6
    """

    @property
    def hgrid(self):
        return self.hgrid_ds
    
    @property
    def vgrid(self):
        return self.vgrid_ds
    
    @property
    def hgrid_path(self):
        return ("Not implemented yet")

    @property
    def vgrid_path(self):
        return ("Not implemented yet")

    def __init__(self, latitude_extent=None, longitude_extent=None, resolution=None):
        self.latitude_extent = latitude_extent
        self.longitude_extent = longitude_extent
        self.resolution = resolution
        self.hgrid_ds = None
        self.vgrid_ds = None

    def subset_global_hgrid(self, longitude_extent, latitude_extent, path = '/glade/work/fredc/cesm/grid/MOM6/tx1_12v1/gridgen/ocean_hgrid_trimmed.nc'):
        # Read in Global Supergrid


        try:
            dsg = xr.open_dataset('/glade/work/fredc/cesm/grid/MOM6/tx1_12v1/gridgen/ocean_hgrid_trimmed.nc')
        except:
            raise FileNotFoundError("Global Supergrid not found. We looked here {}. I would instead use the create_rectangular_hgrid method to create a new grid, or pass in a path with 'path='".format(path))
        I_llc, J_llc = find_nearest(dsg.x, dsg.y, min(longitude_extent), min(latitude_extent))
        I_urc, J_urc =  find_nearest(dsg.x, dsg.y, max(longitude_extent), max(latitude_extent))
        ds_nwa = dsg.isel(nx=slice(I_llc[0],I_urc[0])).isel(ny=slice(J_llc[0],J_urc[0]))
        self.hgrid_ds = ds_nwa
        return ds_nwa

    def subset_global_topo(self):
        return

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

        self.longitude_extent = longitude_extent
        self.latitude_extent = latitude_extent
        self.resolution = resolution
        # longitudes are evenly spaced based on resolution and bounds
        nx = int(
            (self.longitude_extent[1] - self.longitude_extent[0])
            / (self.resolution / 2)
        )
        if nx % 2 != 1:
            nx += 1

        lons = np.linspace(
            self.longitude_extent[0], self.longitude_extent[1], nx
        )  # longitudes in degrees

        # Latitudes evenly spaced by dx * cos(central_latitude)
        central_latitude = np.mean(self.latitude_extent)  # degrees
        latitudinal_resolution = self.resolution * np.cos(np.deg2rad(central_latitude))

        ny = (
            int(
                (self.latitude_extent[1] - self.latitude_extent[0])
                / (latitudinal_resolution / 2)
            )
            + 1
        )

        if ny % 2 != 1:
            ny += 1

        lats = np.linspace(
            self.latitude_extent[0], self.latitude_extent[1], ny
        )  # latitudes in degrees

        hgrid = generate_rectangular_hgrid(lons, lats)
        self.hgrid_ds = hgrid
        return hgrid

    def create_vgrid(self, number_vertical_layers, layer_thickness_ratio, depth):
        """
        Generates a vertical grid based on the ``number_vertical_layers``, the ratio
        of largest to smallest layer thickness (``layer_thickness_ratio``) and the
        total ``depth`` parameters.
        (All these parameters are specified at the class level.)
        """

        thicknesses = hyperbolictan_thickness_profile(
            number_vertical_layers, layer_thickness_ratio, depth
        )

        zi = np.cumsum(thicknesses)
        zi = np.insert(zi, 0, 0.0)  # add zi = 0.0 as first interface

        zl = zi[0:-1] + thicknesses / 2  # the mid-points between interfaces zi

        vcoord = xr.Dataset({"zi": ("zi", zi), "zl": ("zl", zl)})

        vcoord["zi"].attrs = {"units": "meters"}
        vcoord["zl"].attrs = {"units": "meters"}

        self.vgrid_ds = vcoord
        return vcoord

    def setup_gebco_bathymetry(
        self,
        *,
        bathymetry_path,
        longitude_coordinate_name="lon",
        latitude_coordinate_name="lat",
        vertical_coordinate_name="elevation",
        fill_channels=False,
        positive_down=False,
        chunks="auto",
    ):
        """
        Cut out and interpolate the chosen bathymetry and then fill inland lakes.

        It's also possible to optionally fill narrow channels (see ``fill_channels``
        below), although narrow channels are less of an issue for models that are
        discretized on an Arakawa C grid, like MOM6.

        Output is saved in the input directory of the experiment.

        Args:
            bathymetry_path (str): Path to the netCDF file with the bathymetry.
            longitude_coordinate_name (Optional[str]): The name of the longitude coordinate in the bathymetry
                dataset at ``bathymetry_path``. For example, for GEBCO bathymetry: ``'lon'`` (default).
            latitude_coordinate_name (Optional[str]): The name of the latitude coordinate in the bathymetry
                dataset at ``bathymetry_path``. For example, for GEBCO bathymetry: ``'lat'`` (default).
            vertical_coordinate_name (Optional[str]): The name of the vertical coordinate in the bathymetry
                dataset at ``bathymetry_path``. For example, for GEBCO bathymetry: ``'elevation'`` (default).
            fill_channels (Optional[bool]): Whether or not to fill in
                diagonal channels. This removes more narrow inlets,
                but can also connect extra islands to land. Default: ``False``.
            positive_down (Optional[bool]): If ``True``, it assumes that
                bathymetry vertical coordinate is positive down. Default: ``False``.
            chunks (Optional Dict[str, str]): Horizontal chunking scheme for the bathymetry, e.g.,
                ``{"longitude": 100, "latitude": 100}``. Use ``'longitude'`` and ``'latitude'`` rather
                than the actual coordinate names in the input file.
        """

        ## Convert the provided coordinate names into a dictionary mapping to the
        ## coordinate names that MOM6 expects.
        coordinate_names = {
            "xh": longitude_coordinate_name,
            "yh": latitude_coordinate_name,
            "elevation": vertical_coordinate_name,
        }
        if chunks != "auto":
            chunks = {
                coordinate_names["xh"]: chunks["longitude"],
                coordinate_names["yh"]: chunks["latitude"],
            }

        bathymetry = xr.open_dataset(bathymetry_path, chunks=chunks)[
            coordinate_names["elevation"]
        ]

        bathymetry = bathymetry.sel(
            {
                coordinate_names["yh"]: slice(
                    self.latitude_extent[0] - 0.5, self.latitude_extent[1] + 0.5
                )
            }  # 0.5 degree latitude buffer (hardcoded) for regridding
        ).astype("float")

        ## Check if the original bathymetry provided has a longitude extent that goes around the globe
        ## to take care of the longitude seam when we slice out the regional domain.

        horizontal_resolution = (
            bathymetry[coordinate_names["xh"]][1]
            - bathymetry[coordinate_names["xh"]][0]
        )

        horizontal_extent = (
            bathymetry[coordinate_names["xh"]][-1]
            - bathymetry[coordinate_names["xh"]][0]
            + horizontal_resolution
        )

        longitude_buffer = 0.5  # 0.5 degree longitude buffer (hardcoded) for regridding

        if np.isclose(horizontal_extent, 360):
            ## longitude extent that goes around the globe -- use longitude_slicer
            bathymetry = longitude_slicer(
                bathymetry,
                np.array(self.longitude_extent)
                + np.array([-longitude_buffer, longitude_buffer]),
                coordinate_names["xh"],
            )
        else:
            ## otherwise, slice normally
            bathymetry = bathymetry.sel(
                {
                    coordinate_names["xh"]: slice(
                        self.longitude_extent[0] - longitude_buffer,
                        self.longitude_extent[1] + longitude_buffer,
                    )
                }
            )

        bathymetry.attrs["missing_value"] = -1e20  # missing value expected by FRE tools
        bathymetry_output = xr.Dataset({"elevation": bathymetry})
        bathymetry.close()

        bathymetry_output = bathymetry_output.rename(
            {coordinate_names["xh"]: "lon", coordinate_names["yh"]: "lat"}
        )
        bathymetry_output.lon.attrs["units"] = "degrees_east"
        bathymetry_output.lat.attrs["units"] = "degrees_north"
        bathymetry_output.elevation.attrs["_FillValue"] = -1e20
        bathymetry_output.elevation.attrs["units"] = "meters"
        bathymetry_output.elevation.attrs["standard_name"] = (
            "height_above_reference_ellipsoid"
        )
        bathymetry_output.elevation.attrs["long_name"] = (
            "Elevation relative to sea level"
        )
        bathymetry_output.elevation.attrs["coordinates"] = "lon lat"
        bathymetry_output.to_netcdf(
            self.mom_input_dir / "bathymetry_original.nc", mode="w", engine="netcdf4"
        )

        tgrid = xr.Dataset(
            {
                "lon": (
                    ["lon"],
                    self.hgrid.x.isel(nxp=slice(1, None, 2), nyp=1).values,
                ),
                "lat": (
                    ["lat"],
                    self.hgrid.y.isel(nxp=1, nyp=slice(1, None, 2)).values,
                ),
            }
        )
        tgrid = xr.Dataset(
            data_vars={
                "elevation": (
                    ["lat", "lon"],
                    np.zeros(
                        self.hgrid.x.isel(
                            nxp=slice(1, None, 2), nyp=slice(1, None, 2)
                        ).shape
                    ),
                )
            },
            coords={
                "lon": (
                    ["lon"],
                    self.hgrid.x.isel(nxp=slice(1, None, 2), nyp=1).values,
                ),
                "lat": (
                    ["lat"],
                    self.hgrid.y.isel(nxp=1, nyp=slice(1, None, 2)).values,
                ),
            },
        )

        # rewrite chunks to use lat/lon now for use with xesmf
        if chunks != "auto":
            chunks = {
                "lon": chunks[coordinate_names["xh"]],
                "lat": chunks[coordinate_names["yh"]],
            }

        tgrid = tgrid.chunk(chunks)
        tgrid.lon.attrs["units"] = "degrees_east"
        tgrid.lon.attrs["_FillValue"] = 1e20
        tgrid.lat.attrs["units"] = "degrees_north"
        tgrid.lat.attrs["_FillValue"] = 1e20
        tgrid.elevation.attrs["units"] = "meters"
        tgrid.elevation.attrs["coordinates"] = "lon lat"
        tgrid.to_netcdf(
            self.mom_input_dir / "bathymetry_unfinished.nc", mode="w", engine="netcdf4"
        )
        tgrid.close()

        ## Replace subprocess run with regular regridder
        print(
            "Begin regridding bathymetry...\n\n"
            + "If this process hangs it means that the chosen domain might be too big to handle this way. "
            + "After ensuring access to appropriate computational resources, try calling ESMF "
            + "directly from a terminal in the input directory via\n\n"
            + "mpirun -np `NUMBER_OF_CPUS` ESMF_Regrid -s bathymetry_original.nc -d bathymetry_unfinished.nc -m bilinear --src_var elevation --dst_var elevation --netcdf4 --src_regional --dst_regional\n\n"
            + "For details see https://xesmf.readthedocs.io/en/latest/large_problems_on_HPC.html\n\n"
            + "Afterwards, we run 'tidy_bathymetry' method to skip the expensive interpolation step, and finishing metadata, encoding and cleanup."
        )

        # If we have a domain large enough for chunks, we'll run regridder with parallel=True
        parallel = True
        if len(tgrid.chunks) != 2:
            parallel = False
        print(f"Regridding in parallel: {parallel}")
        bathymetry_output = bathymetry_output.chunk(chunks)
        # return
        regridder = xe.Regridder(
            bathymetry_output, tgrid, "bilinear", parallel=parallel
        )

        bathymetry = regridder(bathymetry_output)
        bathymetry.to_netcdf(
            self.mom_input_dir / "bathymetry_unfinished.nc", mode="w", engine="netcdf4"
        )
        print(
            "Regridding finished. Now calling `tidy_bathymetry` method for some finishing touches..."
        )

        self.tidy_bathymetry(fill_channels, positive_down)

    def tidy_bathymetry(self, fill_channels=False, positive_down=True):
        """
        An auxiliary function for bathymetry used to fix up the metadata and remove inland
        lakes after regridding the bathymetry. Having `tidy_bathymetry` as a separate
        method from :func:`~setup_bathymetry` allows for the regridding to be done separately,
        since regridding can be really expensive for large domains.

        If the bathymetry is already regridded and what is left to be done is fixing the metadata
        or fill in some channels, then call this function directly to read in the existing
        ``bathymetry_unfinished.nc`` file that should be in the input directory.

        Args:
            fill_channels (Optional[bool]): Whether to fill in
                diagonal channels. This removes more narrow inlets,
                but can also connect extra islands to land. Default: ``False``.
            positive_down (Optional[bool]): If ``True`` (default), assume that
                bathymetry vertical coordinate is positive down.
        """

        ## reopen bathymetry to modify
        print("Reading in regridded bathymetry to fix up metadata...", end="")
        bathymetry = xr.open_dataset(
            self.mom_input_dir / "bathymetry_unfinished.nc", engine="netcdf4"
        )

        ## Ensure correct encoding
        bathymetry = xr.Dataset(
            {"depth": (["ny", "nx"], bathymetry["elevation"].values)}
        )
        bathymetry.attrs["depth"] = "meters"
        bathymetry.attrs["standard_name"] = "bathymetric depth at T-cell centers"
        bathymetry.attrs["coordinates"] = "zi"

        bathymetry.expand_dims("tiles", 0)

        if not positive_down:
            ## Ensure that coordinate is positive down!
            bathymetry["depth"] *= -1

        ## REMOVE INLAND LAKES

        ocean_mask = xr.where(bathymetry.copy(deep=True).depth <= self.min_depth, 0, 1)
        land_mask = np.abs(ocean_mask - 1)

        changed = True  ## keeps track of whether solution has converged or not

        forward = True  ## only useful for iterating through diagonal channel removal. Means iteration goes SW -> NE

        while changed == True:
            ## First fill in all lakes.
            ## scipy.ndimage.binary_fill_holes fills holes made of 0's within a field of 1's
            land_mask[:, :] = binary_fill_holes(land_mask.data)
            ## Get the ocean mask instead of land- easier to remove channels this way
            ocean_mask = np.abs(land_mask - 1)

            ## Now fill in all one-cell-wide channels
            newmask = xr.where(
                ocean_mask * (land_mask.shift(nx=1) + land_mask.shift(nx=-1)) == 2, 1, 0
            )
            newmask += xr.where(
                ocean_mask * (land_mask.shift(ny=1) + land_mask.shift(ny=-1)) == 2, 1, 0
            )

            if fill_channels == True:
                ## fill in all one-cell-wide horizontal channels
                newmask = xr.where(
                    ocean_mask * (land_mask.shift(nx=1) + land_mask.shift(nx=-1)) == 2,
                    1,
                    0,
                )
                newmask += xr.where(
                    ocean_mask * (land_mask.shift(ny=1) + land_mask.shift(ny=-1)) == 2,
                    1,
                    0,
                )
                ## Diagonal channels
                if forward == True:
                    ## horizontal channels
                    newmask += xr.where(
                        (ocean_mask * ocean_mask.shift(nx=1))
                        * (
                            land_mask.shift({"nx": 1, "ny": 1})
                            + land_mask.shift({"ny": -1})
                        )
                        == 2,
                        1,
                        0,
                    )  ## up right & below
                    newmask += xr.where(
                        (ocean_mask * ocean_mask.shift(nx=1))
                        * (
                            land_mask.shift({"nx": 1, "ny": -1})
                            + land_mask.shift({"ny": 1})
                        )
                        == 2,
                        1,
                        0,
                    )  ## down right & above
                    ## Vertical channels
                    newmask += xr.where(
                        (ocean_mask * ocean_mask.shift(ny=1))
                        * (
                            land_mask.shift({"nx": 1, "ny": 1})
                            + land_mask.shift({"nx": -1})
                        )
                        == 2,
                        1,
                        0,
                    )  ## up right & left
                    newmask += xr.where(
                        (ocean_mask * ocean_mask.shift(ny=1))
                        * (
                            land_mask.shift({"nx": -1, "ny": 1})
                            + land_mask.shift({"nx": 1})
                        )
                        == 2,
                        1,
                        0,
                    )  ## up left & right

                    forward = False

                if forward == False:
                    ## Horizontal channels
                    newmask += xr.where(
                        (ocean_mask * ocean_mask.shift(nx=-1))
                        * (
                            land_mask.shift({"nx": -1, "ny": 1})
                            + land_mask.shift({"ny": -1})
                        )
                        == 2,
                        1,
                        0,
                    )  ## up left & below
                    newmask += xr.where(
                        (ocean_mask * ocean_mask.shift(nx=-1))
                        * (
                            land_mask.shift({"nx": -1, "ny": -1})
                            + land_mask.shift({"ny": 1})
                        )
                        == 2,
                        1,
                        0,
                    )  ## down left & above
                    ## Vertical channels
                    newmask += xr.where(
                        (ocean_mask * ocean_mask.shift(ny=-1))
                        * (
                            land_mask.shift({"nx": 1, "ny": -1})
                            + land_mask.shift({"nx": -1})
                        )
                        == 2,
                        1,
                        0,
                    )  ## down right & left
                    newmask += xr.where(
                        (ocean_mask * ocean_mask.shift(ny=-1))
                        * (
                            land_mask.shift({"nx": -1, "ny": -1})
                            + land_mask.shift({"nx": 1})
                        )
                        == 2,
                        1,
                        0,
                    )  ## down left & right

                    forward = True

            newmask = xr.where(newmask > 0, 1, 0)
            changed = np.max(newmask) == 1
            land_mask += newmask

        self.ocean_mask = np.abs(land_mask - 1)

        bathymetry["depth"] *= self.ocean_mask

        bathymetry["depth"] = bathymetry["depth"].where(
            bathymetry["depth"] != 0, np.nan
        )

        bathymetry.expand_dims({"ntiles": 1}).to_netcdf(
            self.mom_input_dir / "bathymetry.nc",
            mode="w",
            encoding={"depth": {"_FillValue": None}},
        )

        print("done.")
        self.bathymetry = bathymetry


def hyperbolictan_thickness_profile(nlayers, ratio, total_depth):
    """Generate a hyperbolic tangent thickness profile with ``nlayers`` vertical
    layers and total depth of ``total_depth`` whose bottom layer is (about) ``ratio``
    times larger than the top layer.

    The thickness profile transitions from the top-layer thickness to
    the bottom-layer thickness via a hyperbolic tangent proportional to
    ``tanh(2π * (k / (nlayers - 1) - 1 / 2))``, where ``k = 0, 1, ..., nlayers - 1``
    is the layer index with ``k = 0`` corresponding to the top-most layer.

    The sum of all layer thicknesses is ``total_depth``.

    Positive parameter ``ratio`` prescribes (approximately) the ratio of the thickness
    of the bottom-most layer to the top-most layer. The final ratio of the bottom-most
    layer to the top-most layer ends up a bit different from the prescribed ``ratio``.
    In particular, the final ratio of the bottom over the top-most layer thickness is
    ``(1 + ratio * exp(2π)) / (ratio + exp(2π))``. This slight departure comes about
    because of the value of the hyperbolic tangent profile at the end-points ``tanh(π)``,
    which is approximately 0.9963 and not 1. Note that because ``exp(2π)`` is much greater
    than 1, the value of the actual ratio is not that different from the prescribed value
    ``ratio``, e.g., for ``ratio`` values between 1/100 and 100 the final ratio of the
    bottom-most layer to the top-most layer only departs from the prescribed ``ratio``
    by ±20%.

    Args:
        nlayers (int): Number of vertical layers.
        ratio (float): The desired value of the ratio of bottom-most to
            the top-most layer thickness. Note that the final value of
            the ratio of bottom-most to the top-most layer thickness
            ends up ``(1 + ratio * exp(2π)) / (ratio + exp(2π))``. Must
            be positive.
        total_depth (float): The total depth of grid, i.e., the sum
            of all thicknesses.

    Returns:
        numpy.array: An array containing the layer thicknesses.

    Examples:

        The spacings for a vertical grid with 20 layers, with maximum depth 1000 meters,
        and for which the top-most layer is about 4 times thinner than the bottom-most
        one.

        >>> from regional_mom6 import hyperbolictan_thickness_profile
        >>> nlayers, total_depth = 20, 1000
        >>> ratio = 4
        >>> dz = hyperbolictan_thickness_profile(nlayers, ratio, total_depth)
        >>> dz
        array([20.11183771, 20.2163053 , 20.41767549, 20.80399084, 21.53839043,
               22.91063751, 25.3939941 , 29.6384327 , 36.23006369, 45.08430684,
               54.91569316, 63.76993631, 70.3615673 , 74.6060059 , 77.08936249,
               78.46160957, 79.19600916, 79.58232451, 79.7836947 , 79.88816229])
        >>> dz.sum()
        1000.0
        >>> dz[-1] / dz[0]
        3.9721960481753706

        If we want the top layer to be thicker then we need to prescribe ``ratio < 1``.

        >>> from regional_mom6 import hyperbolictan_thickness_profile
        >>> nlayers, total_depth = 20, 1000
        >>> ratio = 1/4
        >>> dz = hyperbolictan_thickness_profile(nlayers, ratio, total_depth)
        >>> dz
        array([79.88816229, 79.7836947 , 79.58232451, 79.19600916, 78.46160957,
               77.08936249, 74.6060059 , 70.3615673 , 63.76993631, 54.91569316,
               45.08430684, 36.23006369, 29.6384327 , 25.3939941 , 22.91063751,
               21.53839043, 20.80399084, 20.41767549, 20.2163053 , 20.11183771])
        >>> dz.sum()
        1000.0
        >>> dz[-1] / dz[0]
        0.25174991059652

        Now how about a grid with the same total depth as above but with equally-spaced
        layers.

        >>> from regional_mom6 import hyperbolictan_thickness_profile
        >>> nlayers, total_depth = 20, 1000
        >>> ratio = 1
        >>> dz = hyperbolictan_thickness_profile(nlayers, ratio, total_depth)
        >>> dz
        array([50., 50., 50., 50., 50., 50., 50., 50., 50., 50., 50., 50., 50.,
               50., 50., 50., 50., 50., 50., 50.])
    """

    assert isinstance(nlayers, int), "nlayers must be an integer"

    if nlayers == 1:
        return np.array([float(total_depth)])

    assert ratio > 0, "ratio must be > 0"

    # The hyberbolic tangent profile below implies that the sum of
    # all layer thicknesses is:
    #
    # nlayers * (top_layer_thickness + bottom_layer_thickness) / 2
    #
    # By choosing the top_layer_thickness appropriately we ensure that
    # the sum of all layer thicknesses is the prescribed total_depth.
    top_layer_thickness = 2 * total_depth / (nlayers * (1 + ratio))

    bottom_layer_thickness = ratio * top_layer_thickness

    layer_thicknesses = top_layer_thickness + 0.5 * (
        bottom_layer_thickness - top_layer_thickness
    ) * (1 + np.tanh(2 * np.pi * (np.arange(nlayers) / (nlayers - 1) - 1 / 2)))

    sum_of_thicknesses = np.sum(layer_thicknesses)

    atol = np.finfo(type(sum_of_thicknesses)).eps

    assert np.isclose(total_depth, sum_of_thicknesses, atol=atol)  # just checking ;)

    return layer_thicknesses


def generate_rectangular_hgrid(lons, lats):
    """
    Construct a horizontal grid with all the metadata required by MOM6, based on
    arrays of longitudes (``lons``) and latitudes (``lats``) on the supergrid.
    Here, 'supergrid' refers to both cell edges and centres, meaning that there
    are twice as many points along each axis than for any individual field.

    Caution:
        It is assumed the grid's boundaries are lines of constant latitude and
        longitude. Rotated grids need to be handled differently.

        It is also assumed here that the longitude array values are uniformly spaced.

        Ensure both ``lons`` and ``lats`` are monotonically increasing.

    Args:
        lons (numpy.array): All longitude points on the supergrid. Must be uniformly spaced.
        lats (numpy.array): All latitude points on the supergrid.

    Returns:
        xarray.Dataset: An FMS-compatible horizontal grid (``hgrid``) that includes all required attributes.
    """

    assert np.all(
        np.diff(lons) > 0
    ), "longitudes array lons must be monotonically increasing"
    assert np.all(
        np.diff(lats) > 0
    ), "latitudes array lats must be monotonically increasing"

    R = 6371e3  # mean radius of the Earth; https://en.wikipedia.org/wiki/Earth_radius

    # compute longitude spacing and ensure that longitudes are uniformly spaced
    dlons = lons[1] - lons[0]

    assert np.allclose(
        np.diff(lons), dlons * np.ones(np.size(lons) - 1)
    ), "provided array of longitudes must be uniformly spaced"

    # dx = R * cos(np.deg2rad(lats)) * np.deg2rad(dlons) / 2
    # Note: division by 2 because we're on the supergrid
    dx = np.broadcast_to(
        R * np.cos(np.deg2rad(lats)) * np.deg2rad(dlons) / 2,
        (lons.shape[0] - 1, lats.shape[0]),
    ).T

    # dy = R * np.deg2rad(dlats) / 2
    # Note: division by 2 because we're on the supergrid
    dy = np.broadcast_to(
        R * np.deg2rad(np.diff(lats)) / 2, (lons.shape[0], lats.shape[0] - 1)
    ).T

    lon, lat = np.meshgrid(lons, lats)

    area = quadrilateral_areas(lat, lon, R)

    attrs = {
        "tile": {
            "standard_name": "grid_tile_spec",
            "geometry": "spherical",
            "north_pole": "0.0 90.0",
            "discretization": "logically_rectangular",
            "conformal": "true",
        },
        "x": {"standard_name": "geographic_longitude", "units": "degree_east"},
        "y": {"standard_name": "geographic_latitude", "units": "degree_north"},
        "dx": {
            "standard_name": "grid_edge_x_distance",
            "units": "meters",
        },
        "dy": {
            "standard_name": "grid_edge_y_distance",
            "units": "meters",
        },
        "area": {
            "standard_name": "grid_cell_area",
            "units": "m**2",
        },
        "angle_dx": {
            "standard_name": "grid_vertex_x_angle_WRT_geographic_east",
            "units": "degrees_east",
        },
        "arcx": {
            "standard_name": "grid_edge_x_arc_type",
            "north_pole": "0.0 90.0",
        },
    }

    return xr.Dataset(
        {
            "tile": ((), np.array(b"tile1", dtype="|S255"), attrs["tile"]),
            "x": (["nyp", "nxp"], lon, attrs["x"]),
            "y": (["nyp", "nxp"], lat, attrs["y"]),
            "dx": (["nyp", "nx"], dx, attrs["dx"]),
            "dy": (["ny", "nxp"], dy, attrs["dy"]),
            "area": (["ny", "nx"], area, attrs["area"]),
            "angle_dx": (["nyp", "nxp"], lon * 0, attrs["angle_dx"]),
            "arcx": ((), np.array(b"small_circle", dtype="|S255"), attrs["arcx"]),
        }
    )


def longitude_slicer(data, longitude_extent, longitude_coords):
    """
    Slice longitudes while handling periodicity and the 'seams', that is the
    longitude values where the data wraps around in a global domain (for example,
    longitudes are defined, usually, within domain [0, 360] or [-180, 180]).

    The algorithm works in five steps:

    - Determine whether we need to add or subtract 360 to get the middle of the
      ``longitude_extent`` to lie within ``data``'s longitude range (hereby ``old_lon``).

    - Shift the dataset so that its midpoint matches the midpoint of
      ``longitude_extent`` (up to a multiple of 360). Now, the modified ``old_lon``
      does not increase monotonically from West to East since the 'seam'
      has moved.

    - Fix ``old_lon`` to make it monotonically increasing again. This uses
      the information we have about the way the dataset was shifted/rolled.

    - Slice the ``data`` index-wise. We know that ``|longitude_extent[1] - longitude_extent[0]| / 360``
      multiplied by the number of discrete longitude points in the global input data gives
      the number of longitude points in our slice, and we've already set the midpoint
      to be the middle of the target domain.

    - Finally re-add the correct multiple of 360 so the whole domain matches
      the target.

    Args:
        data (xarray.Dataset): The global data you want to slice in longitude.
        longitude_extent (Tuple[float, float]): The target longitudes (in degrees)
            we want to slice to. Must be in increasing order.
        longitude_coords (Union[str, list[str]): The name or list of names of the
            longitude coordinates(s) in ``data``.
    Returns:
        xarray.Dataset: The sliced ``data``.
    """

    if isinstance(longitude_coords, str):
        longitude_coords = [longitude_coords]

    for lon in longitude_coords:
        central_longitude = np.mean(longitude_extent)  ## Midpoint of target domain

        ## Find a corresponding value for the intended domain midpoint in our data.
        ## It's assumed that data has equally-spaced longitude values.

        lons = data[lon].data
        dlons = lons[1] - lons[0]

        assert np.allclose(
            np.diff(lons), dlons * np.ones(np.size(lons) - 1)
        ), "provided longitude coordinate must be uniformly spaced"

        for i in range(-1, 2, 1):
            if data[lon][0] <= central_longitude + 360 * i <= data[lon][-1]:

                ## Shifted version of target midpoint; e.g., could be -90 vs 270
                ## integer i keeps track of what how many multiples of 360 we need to shift entire
                ## grid by to match central_longitude
                _central_longitude = central_longitude + 360 * i

                ## Midpoint of the data
                central_data = data[lon][data[lon].shape[0] // 2].values

                ## Number of indices between the data midpoint and the target midpoint.
                ## Sign indicates direction needed to shift.
                shift = int(
                    -(data[lon].shape[0] * (_central_longitude - central_data)) // 360
                )

                ## Shift data so that the midpoint of the target domain is the middle of
                ## the data for easy slicing.
                new_data = data.roll({lon: 1 * shift}, roll_coords=True)

                ## Create a new longitude coordinate.
                ## We'll modify this to remove any seams (i.e., jumps like -270 -> 90)
                new_lon = new_data[lon].values

                ## Take the 'seam' of the data, and either backfill or forward fill based on
                ## whether the data was shifted F or west
                if shift > 0:
                    new_seam_index = shift

                    new_lon[0:new_seam_index] -= 360

                if shift < 0:
                    new_seam_index = data[lon].shape[0] + shift

                    new_lon[new_seam_index:] += 360

                ## new_lon is used to re-centre the midpoint to match that of target domain
                new_lon -= i * 360

                new_data = new_data.assign_coords({lon: new_lon})

                ## Choose the number of lon points to take from the middle, including a buffer.
                ## Use this to index the new global dataset
                num_lonpoints = (
                    int(data[lon].shape[0] * (central_longitude - longitude_extent[0]))
                    // 360
                )

        data = new_data.isel(
            {
                lon: slice(
                    data[lon].shape[0] // 2 - num_lonpoints,
                    data[lon].shape[0] // 2 + num_lonpoints,
                )
            }
        )

    return data

def spherical2cartesian(lon, lat):
    '''
    Convert spherical coordinates to cartesian coordinates 
    '''
    R_earth=6378136 # meters
    lonr = np.deg2rad(lon)
    latr = np.deg2rad(lat)
    x = R_earth * np.cos(latr) * np.cos(lonr)
    y = R_earth * np.cos(latr) * np.sin(lonr)
    z = R_earth * np.sin(latr)
    return x, y, z

def create_tree(lon, lat):
    '''
    Create a K-d tree from the spherical coordinates, which is good for spatial queries, like nearest neighbor search
    '''
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

def find_nearest(lon, lat, lon_pt, lat_pt):
    '''
    Find the nearest point to lon_pt, lat_pt in the grid defined by lon, lat
    '''
    # Create a tree from the grid
    tree = create_tree(lon, lat)

    # Get Cartesian coordinates of the point of interest
    xp, yp, zp = spherical2cartesian(lon_pt, lat_pt)

    # Find nearest index
    _, idx = tree.query(np.column_stack((xp, yp, zp)))
    
    #idx = np.unique(idx) # Remove duplicates

    # Format and return the index
    idx = np.unravel_index(idx, lon.shape)
    Iidx = idx[1]
    Jidx = idx[0]
    return Iidx, Jidx