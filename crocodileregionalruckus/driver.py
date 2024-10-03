import logging
driver_logger = logging.getLogger(__name__)
import datetime as dt
import xarray as xr
import json
import os




class crr_experiment:
    """The main class for setting up a regional experiment.

    Everything about the regional experiment.

    Methods in this class generate the various input files needed for a MOM6
    experiment forced with open boundary conditions (OBCs). The code is agnostic
    to the user's choice of boundary forcing, bathymetry, and surface forcing;
    users need to prescribe what variables are all called via mapping dictionaries
    from MOM6 variable/coordinate name to the name in the input dataset.

    The class can be used to generate the grids for a new experiment, or to read in
    an existing one (when ``read_existing_grids=True``; see argument description below).

    Args:
        longitude_extent (Tuple[float]): Extent of the region in longitude (in degrees). For
            example: ``(40.5, 50.0)``.
        latitude_extent (Tuple[float]): Extent of the region in latitude (in degrees). For
            example: ``(-20.0, 30.0)``.
        date_range (Tuple[str]): Start and end dates of the boundary forcing window. For
            example: ``("2003-01-01", "2003-01-31")``.
        resolution (float): Lateral resolution of the domain (in degrees).
        number_vertical_layers (int): Number of vertical layers.
        layer_thickness_ratio (float): Ratio of largest to smallest layer thickness;
            used as input in :func:`~hyperbolictan_thickness_profile`.
        depth (float): Depth of the domain.
        mom_run_dir (str): Path of the MOM6 control directory.
        mom_input_dir (str): Path of the MOM6 input directory, to receive the forcing files.
        toolpath_dir (str): Path of GFDL's FRE tools (https://github.com/NOAA-GFDL/FRE-NCtools)
            binaries.
        grid_type (Optional[str]): Type of horizontal grid to generate.
            Currently, only ``'even_spacing'`` is supported.
        repeat_year_forcing (Optional[bool]): When ``True`` the experiment runs with
            repeat-year forcing. When ``False`` (default) then inter-annual forcing is used.
        read_existing_grids (Optional[Bool]): When ``True``, instead of generating the grids,
            the grids and the ocean mask are being read from within the ``mom_input_dir`` and
            ``mom_run_dir`` directories. Useful for modifying or troubleshooting experiments.
            Default: ``False``.
        minimum_depth (Optional[int]): The minimum depth in meters of a grid cell allowed before it is masked out and treated as land.
    """

    def __init__(
        self,
        longitude_extent=None,
        latitude_extent=None,
        date_range=None,
        resolution=None,
        number_vertical_layers=None,
        layer_thickness_ratio=None,
        depth=None,
        mom_run_dir=None,
        mom_input_dir=None,
        toolpath_dir=None,
        grid_type="even_spacing",
        repeat_year_forcing=False,
        minimum_depth=4,
        tidal_constituents=["M2"],
        name=None,
    ):
        # ## Set up the experiment with no config file
        ## in case list was given, convert to tuples
        self.expt_name = name
        self.tidal_constituents = tidal_constituents
        self.repeat_year_forcing = repeat_year_forcing
        self.grid_type = grid_type
        self.toolpath_dir = toolpath_dir
        self.mom_run_dir = mom_run_dir
        self.mom_input_dir = mom_input_dir
        self.min_depth = minimum_depth
        self.depth = depth
        self.layer_thickness_ratio = layer_thickness_ratio
        self.number_vertical_layers = number_vertical_layers
        self.resolution = resolution
        self.latitude_extent = latitude_extent
        self.longitude_extent = longitude_extent
        self.ocean_mask = None
        self.layout = None


        try:
            self.date_range = [
                dt.datetime.strptime(date_range[0], "%Y-%m-%d %H:%M:%S"),
                dt.datetime.strptime(date_range[1], "%Y-%m-%d %H:%M:%S"),
            ]
        except:
            driver_logger.warning("Date range not formatted correctly. Please use 'YYYY-MM-DD HH:MM:SS' format in a list or tuple of two.")

    def setup_directories(self):
        self.mom_run_dir.mkdir(exist_ok=True)
        self.mom_input_dir.mkdir(exist_ok=True)        
        (self.mom_input_dir / "weights").mkdir(exist_ok=True)
        (self.mom_input_dir / "forcing").mkdir(exist_ok=True)

        run_inputdir = self.mom_run_dir / "inputdir"
        if not run_inputdir.exists():
            run_inputdir.symlink_to(self.mom_input_dir.resolve())
        input_rundir = self.mom_input_dir / "rundir"
        if not input_rundir.exists():
            input_rundir.symlink_to(self.mom_run_dir.resolve())

    def __str__(self) -> str:
        return json.dumps(self.write_config_file(export=False, quiet=True), indent=4)
    
    def write_config_file(self, path=None, export=True, quiet=False):
        """
        Write a configuration file for the experiment. This is a simple json file
        that contains the expirment object information to allow for reproducibility, to pick up where a user left off, and
        to make information about the expirement readable.
        """
        if not quiet:
            print("Writing Config File.....")
        ## check if files exist
        vgrid_path = None
        hgrid_path = None
        if os.path.exists(self.mom_input_dir / "vcoord.nc"):
            vgrid_path = self.mom_input_dir / "vcoord.nc"
        if os.path.exists(self.mom_input_dir / "hgrid.nc"):
            hgrid_path = self.mom_input_dir / "hgrid.nc"

        try:
            date_range = [
                self.date_range[0].strftime("%Y-%m-%d"),
                self.date_range[1].strftime("%Y-%m-%d"),
            ]
        except:
            date_range = None
        config_dict = {
            "name": self.expt_name,
            "date_range": date_range,
            "latitude_extent": self.latitude_extent,
            "longitude_extent": self.longitude_extent,
            "run_dir": str(self.mom_run_dir),
            "input_dir": str(self.mom_input_dir),
            "toolpath_dir": str(self.toolpath_dir),
            "resolution": self.resolution,
            "number_vertical_layers": self.number_vertical_layers,
            "layer_thickness_ratio": self.layer_thickness_ratio,
            "depth": self.depth,
            "grid_type": self.grid_type,
            "repeat_year_forcing": self.repeat_year_forcing,
            "ocean_mask": self.ocean_mask,
            "layout": self.layout,
            "min_depth": self.min_depth,
            "vgrid": str(vgrid_path),
            "hgrid": str(hgrid_path),
            "bathymetry": self.bathymetry_property,
            "ocean_state": self.ocean_state_boundaries,
            "tides": self.tides_boundaries,
            "initial_conditions": self.initial_condition,
            "tidal_constituents": self.tidal_constituents,
        }
        if export:
            if path is not None:
                export_path = path
            else:
                export_path = self.mom_run_dir / "rmom6_config.json"
            with open(export_path, "w") as f:
                json.dump(
                    config_dict,
                    f,
                    indent=4,
                )
        if not quiet:
            print("Done.")
        return config_dict
        


