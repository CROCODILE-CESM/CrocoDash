# Grid Stuff (Supergrid, Bathymetry, Vgrid)

In CrocoDash, the first step of any workflow is grid generation. CrocoDash wraps
[mom6_forge](https://github.com/NCAR/mom6_forge) directly with no modifications,
so **all grid documentation lives in the
[mom6_forge docs](https://ncar.github.io/mom6_forge/)**.

## Importing

The only difference from vanilla mom6_forge is the import path. Replace the
`mom6_forge` namespace with `CrocoDash`:

| Instead of... | Use... |
|---|---|
| `import mom6_forge.grid` | `import CrocoDash.grid` |
| `import mom6_forge.topo` | `import CrocoDash.topo` |
| `import mom6_forge.vgrid` | `import CrocoDash.vgrid` |

Everything else — class names, method signatures, parameters — is identical.

## Next Steps

Once you have your `Grid`, `Topo`, and `VGrid` objects ready, pass them to the
`Case` object to move on to case setup:

```python
case = cd.Case(grid=grid, topo=topo, vgrid=vgrid, ...)
```

See the [mom6_forge documentation](https://ncar.github.io/mom6_forge/) for full
details on creating and configuring your grid objects, including the interactive
`TopoEditor` for manual bathymetry adjustments.