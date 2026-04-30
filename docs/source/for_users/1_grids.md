# 1. Grids (hgrid · topo · vgrid)

The first step of any CrocoDash workflow is defining the spatial domain: a
horizontal grid (`Grid`), a bathymetry (`Topo`), and a vertical grid (`VGrid`).

```{mermaid}
flowchart LR
    HG["hgrid<br/>(Grid)"] --> C["Case(...)"]
    TP["topo<br/>(Topo)"] --> C
    VG["vgrid<br/>(VGrid)"] --> C
```

CrocoDash re-exports these objects from [mom6_forge](https://github.com/NCAR/mom6_forge)
**with no modifications**, so all the details — class methods, creation
patterns, file formats — live in the
[mom6_forge documentation](https://ncar.github.io/mom6_forge/). This page is
a short on-ramp that points you there.

## What mom6_forge gives you

For each of the three grid objects, mom6_forge provides both programmatic and
interactive construction:

| Object | Programmatic API | Interactive widget |
|---|---|---|
| Horizontal grid (`Grid`) | `Grid(...)`, `Grid.from_supergrid(...)` | `GridCreator` |
| Bathymetry (`Topo`) | `Topo(...)`, `Topo.from_topo_file(...)` | `TopoEditor` |
| Vertical grid (`VGrid`) | `VGrid.hyperbolic(...)`, `VGrid.from_file(...)` | `VGridCreator` |

Notable features worth knowing about:

- **`TopoEditor`** — ipywidgets-based bathymetry editor with undo/redo,
  version-controlled edits, and live plotting. Great for fixing isolated
  basins, carving channels, or smoothing coastlines before case creation.
- **Version-controlled bathymetry** — `Topo` uses a per-domain `TopoLibrary/`
  directory under the hood. Every edit is committed as a git-style operation,
  so you can replay, share, or undo bathymetry changes reproducibly.
- **Curvilinear grids** — `Grid.from_supergrid(...)` works for both
  rectilinear (lon/lat) and curvilinear grids.
- **ESMF mesh + SCRIP output** — the `Topo` object writes CICE grids, SCRIP
  grids, and ESMF meshes directly, which is what CESM needs for coupling.
- **Chlorophyll and runoff mapping helpers** — `mom6_forge.chl` and
  `mom6_forge.mapping` are used internally by `extract_forcings`, but are also
  available if you need them directly.

## Importing

The only difference from vanilla mom6_forge is the import path. Replace the
`mom6_forge` namespace with `CrocoDash`:

| Instead of... | Use... |
|---|---|
| `import mom6_forge.grid` | `import CrocoDash.grid` |
| `import mom6_forge.topo` | `import CrocoDash.topo` |
| `import mom6_forge.vgrid` | `import CrocoDash.vgrid` |

Everything else — class names, method signatures, parameters — is identical.

## Next step

Once you have your `Grid`, `Topo`, and `VGrid` objects ready, pass them to the
`Case` object to move on to [Case Setup](2_case_setup.md):

```python
case = cd.Case(
    ocn_grid=grid,
    ocn_topo=topo,
    ocn_vgrid=vgrid,
    ...
)
```

## See also

- [mom6_forge documentation](https://ncar.github.io/mom6_forge/) — full grid API
- [Submodule API Usage](../for_developers/submodule_api_usage.md) — the exact
  mom6_forge functions CrocoDash calls (useful when upgrading mom6_forge)