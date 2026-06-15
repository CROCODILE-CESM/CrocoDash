# Grid Stuff (Supergrid, Bathymetry, Vgrid)

In CrocoDash, the first step is grid generation. CrocoDash directly wraps, with no modifications, mom6_bathy. Please pursue the [mom6_bathy documentation](https://ncar.github.io/mom6_bathy/) for all questions. There is no extra nuance to using CrocoDash grids, the only thing you need to is import the modules through CrocoDash.

## Editing Topography After Case Creation

If you use the `TopoEditor` (or otherwise modify the topography file) **after** creating your CESM case, be aware that:

- If your edits change the **land-sea mask**, the ESMF mesh file (used by CESM for domain decomposition and remapping) must be regenerated to match.
- If you only change depths without changing the mask, regeneration is not necessary.

To regenerate the ESMF mesh from an updated `Topo` object:

```python
topo.write_esmf_mesh(path_to_esmf_mesh_file)
```

The path to the ESMF mesh file for your case is stored as `case.esmf_mesh_path` after case creation, or you can find it in the case's input directory under `ocnice/ESMF_mesh_<gridname>_<id>.nc`.