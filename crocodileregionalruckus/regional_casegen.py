import numpy as np
import xarray as xr
from pathlib import Path
from datetime import datetime
import shutil
import os
import subprocess
import regional_mom6 as rmom6

def write_esmf_mesh(hgrid, bathymetry,save_path, title=None,cyclic_x = False):
    """
    Write the ESMF mesh file

    This function is adapted from Alper Altuntas' NCAR/mom6_bathy library. 
    Modifications allow the function to work in isolation from the rest of the package.


    Parameters
    ----------
    hgrid: xarray dataset
        horizontal grid (supergrid) for MOM6
    ocean_mask: xarray dataset
        land/ocean mask for MOM6 run. 1 is ocean, 0 is land
    save_path: str
        Path to ESMF mesh file to be written.
    title: str, optional
        File title.
    """

    ds = xr.Dataset()

    # global attrs:
    ds.attrs["gridType"] = "unstructured mesh"
    ds.attrs["date_created"] = datetime.now().isoformat()
    if title:
        ds.attrs["title"] = title

    tlon_flat = hgrid.x[1:-1:2,1:-1:2].values.flatten() # Extract the T point cells from the hgrid
    tlat_flat = hgrid.y[1:-1:2,1:-1:2].values.flatten()
    ncells = len(tlon_flat)  # i.e., elementCount in ESMF mesh nomenclature

    coord_units = "degrees" # Hardcode this to degrees rather than read in from supergrid

    ds["centerCoords"] = xr.DataArray(
        [[tlon_flat[i], tlat_flat[i]] for i in range(ncells)],
        dims=["elementCount", "coordDim"],
        attrs={"units": coord_units},
    )

    ds["numElementConn"] = xr.DataArray(
        np.full(ncells, 4).astype(np.int8),
        dims=["elementCount"],
        attrs={"long_name": "Node indices that define the element connectivity"},
    )

    tarea = xr.DataArray(
                hgrid.area[::2, ::2]
                + hgrid.area[1::2, 1::2]
                + hgrid.area[::2, 1::2]
                + hgrid.area[::2, 1::2],
                dims=["ny", "nx"],
                attrs={"name": "area of t-cells", "units": "meters^2"},
            )


    ds["elementArea"] = xr.DataArray(
        tarea.values.flatten(), # Read in the area from existing hgrid T cells
        dims=["elementCount"],
        attrs={"units": "m**2"}, # These units are hardcoded to match the regular mom6 hgrid
    )

    ocean_mask = xr.where(bathymetry.depth.fillna(0) != 0,1,0)

    ds["elementMask"] = xr.DataArray(
        ocean_mask.values.astype(np.int32).flatten(), dims=["elementCount"]
    )

    i0 = 1  # start index for node id's

    if cyclic_x:

        nx, ny = len(hgrid.nx) // 2, len(hgrid.ny) // 2
        qlon_flat = hgrid.x[0:-1:2,1:-1:2].values[:, :-1].flatten()
        qlat_flat = hgrid.y[0:-1:2,1:-1:2].values[:, :-1].flatten()
        nnodes = len(qlon_flat)
        assert nnodes == nx * (ny + 1)

        # Below returns element connectivity of i-th element
        # (assuming 0 based node and element indexing)
        get_element_conn = lambda i: [
            i0 + i % nx + (i // nx) * (nx),
            i0 + i % nx + (i // nx) * (nx) + 1 - (((i + 1) % nx) == 0) * nx,
            i0 + i % nx + (i // nx + 1) * (nx) + 1 - (((i + 1) % nx) == 0) * nx,
            i0 + i % nx + (i // nx + 1) * (nx),
        ]

    else: # non-cyclic grid

        nx, ny = len(hgrid.nx.values) // 2, len(hgrid.ny.values) // 2
        qlon_flat = hgrid.x[0::2,0::2].values.flatten()
        qlat_flat = hgrid.y[0::2,0::2].values.flatten()
        nnodes = len(qlon_flat)
        assert nnodes == (nx + 1) * (ny + 1)

        # Below returns element connectivity of i-th element
        # (assuming 0 based node and element indexing)
        get_element_conn = lambda i: [
            i0 + i % nx + (i // nx) * (nx + 1),
            i0 + i % nx + (i // nx) * (nx + 1) + 1,
            i0 + i % nx + (i // nx + 1) * (nx + 1) + 1,
            i0 + i % nx + (i // nx + 1) * (nx + 1),
        ]


    ds["nodeCoords"] = xr.DataArray(
        np.column_stack((qlon_flat, qlat_flat)),
        dims=["nodeCount", "coordDim"],
        attrs={"units": coord_units},
    )

    ds["elementConn"] = xr.DataArray(
        np.array([get_element_conn(i) for i in range(ncells)]).astype(np.int32),
        dims=["elementCount", "maxNodePElement"],
        attrs={
            "long_name": "Node indices that define the element connectivity",
            "start_index": np.int32(i0),
        },
    )
    ds.to_netcdf(save_path,mode = "w")

    

def setup_cesm(expt,CESMPath,project,cyclic_x = False):
    """
    Given a regional-mom6 experiment object and a path to the CESM folder, this function makes all of the changes to the CESM configuration to get it to run with the regional configuration. 
    """

    nx = int(len(expt.hgrid.nx) //2)
    ny = int(len(expt.hgrid.ny) //2)
    # Copy the configuration files to the SourceMods folder
    print(f"Copying input.nml, diag_table, MOM_input_and MOM_override to {CESMPath / 'SourceMods/src.mom'}")
    for i in ["input.nml", "diag_table", "MOM_input", "MOM_override"]:
        shutil.copy(Path(expt.mom_run_dir) / i, CESMPath / "SourceMods/src.mom")

    # Add NIGLOBAL and NJGLOBAL to MOM_override, and include INPUTDIR pointing to mom6 inputs
    print(f"Adding NIGLOBAL = {nx}, NJGLOBAL = {ny}, and INPUTDIR = {expt.mom_input_dir} to MOM_override")
    with open(CESMPath / "SourceMods/src.mom/MOM_override", "a") as f:
        f.write(f"#override NIGLOBAL = {nx}\n")
        f.write(f"#override NJGLOBAL = {ny}\n")
        f.write(f"#override INPUTDIR = {expt.mom_input_dir}\n")
        f.close()

    # Remove references to MOM_layout in input.nml, as processor layouts are handled by CESM
    print("Removing references to MOM_layout in input.nml")
    with open(CESMPath / "SourceMods/src.mom/input.nml", "r") as f:
        lines = f.readlines()
        f.close()

    print("Add MOM_override to parameter_filename in input.nml")
    with open(CESMPath / "SourceMods/src.mom/input.nml", "w") as f:
        for i in range(len(lines)):
            if 'parameter_filename' in lines[i] and 'MOM_layout' in lines[i]: 
                lines[i] = "parameter_filename = 'MOM_input', 'MOM_override'"
        f.writelines(lines)
        f.close()

    # Move all of the forcing files out of the forcing directory to the main inputdir
    print("Move all of the forcing files out of the forcing directory to the main inputdir")
    for i in expt.mom_input_dir.glob("forcing/*"):
        shutil.move(i, expt.mom_input_dir / i.name)

    # Find and replace instances of forcing/ with nothing in the MOM_input file
    print("Find and replace instances of forcing/ with nothing in the MOM_input file")
    with open(CESMPath / "SourceMods/src.mom/MOM_input", "r") as f:
        lines = f.readlines()
        f.close()
    with open(CESMPath / "SourceMods/src.mom/MOM_input", "w") as f:
        for i in range(len(lines)):
            lines[i] = lines[i].replace("forcing/", "")
        f.writelines(lines)
        f.close()

    # Find and replace instances of forcing/ with nothing in the MOM_input file
    print("Find and replace instances of forcing/ with nothing in the MOM_input file")
    with open(CESMPath / "SourceMods/src.mom/MOM_override", "r") as f:
        lines = f.readlines()
        f.close()
    with open(CESMPath / "SourceMods/src.mom/MOM_override", "w") as f:
        for i in range(len(lines)):
            lines[i] = lines[i].replace("forcing/", "")
        f.writelines(lines)
        f.close()


    # Make ESMF grid and save to inputdir
    print("Make ESMF grid and save to inputdir")
    write_esmf_mesh(expt.hgrid, xr.open_dataset(expt.mom_input_dir / "bathymetry.nc"), expt.mom_input_dir / "esmf_mesh.nc", title="Regional MOM6 grid", cyclic_x = cyclic_x)

    # Make xml changes
    print("Make xml changes. Setting OCN_NX={}, OCN_NY={}".format(nx,ny))
    print("MOM6_MEMORY_MODE=dynamic_symmetric") 
    print("OCN_DOMAIN_MESH, ICE_DOMAIN_MESH, MASK_MESH, MASK_GRID, OCN_GRID, ICE_GRID ={}".format(expt.mom_input_dir / 'esmf_mesh.nc'))
    print("RUN_REFDATE, RUN_STARTDATE = {}".format(expt.date_range[0].strftime('%Y-%m-%d')))
    subprocess.run(f"./xmlchange OCN_NX={nx}",shell = True,cwd = str(CESMPath))
    subprocess.run(f"./xmlchange OCN_NY={ny}",shell = True,cwd = str(CESMPath))
    subprocess.run(f"./xmlchange MOM6_MEMORY_MODE=dynamic_symmetric",shell = True,cwd = str(CESMPath))
    subprocess.run(f"./xmlchange OCN_DOMAIN_MESH={expt.mom_input_dir / 'esmf_mesh.nc'}",shell = True,cwd = str(CESMPath))
    subprocess.run(f"./xmlchange ICE_DOMAIN_MESH={expt.mom_input_dir / 'esmf_mesh.nc'}",shell = True,cwd = str(CESMPath))
    subprocess.run(f"./xmlchange MASK_MESH={expt.mom_input_dir / 'esmf_mesh.nc'}",shell = True,cwd = str(CESMPath))
    subprocess.run(f"./xmlchange MASK_GRID={expt.mom_input_dir / 'esmf_mesh.nc'}",shell = True,cwd = str(CESMPath))
    subprocess.run(f"./xmlchange OCN_GRID={expt.mom_input_dir / 'esmf_mesh.nc'}",shell = True,cwd = str(CESMPath))
    subprocess.run(f"./xmlchange ICE_GRID={expt.mom_input_dir / 'esmf_mesh.nc'}",shell = True,cwd = str(CESMPath))

    subprocess.run(f"./xmlchange RUN_REFDATE={expt.date_range[0].strftime('%Y-%m-%d')}",shell = True,cwd = str(CESMPath))
    subprocess.run(f"./xmlchange RUN_STARTDATE={expt.date_range[0].strftime('%Y-%m-%d')}",shell = True,cwd = str(CESMPath))

    subprocess.run(f"./xmlchange PROJECT={project}",shell = True,cwd = str(CESMPath))
    subprocess.run(f"./xmlchange CHARGE_ACCOUNT={project}",shell = True,cwd = str(CESMPath))
    
    # Now make symlinks from the CESM directory to the mom input directory and the CESM run directory
    print("Make symlinks from the CESM directory to the mom input directory and the CESM run directory")
    with CESMPath / "mom_input_directory" as link:
        link.unlink(missing_ok=True)
        link.symlink_to(expt.mom_input_dir)

    return 


# def regrid_marbl_forcing(expt,marbl_directory):

    