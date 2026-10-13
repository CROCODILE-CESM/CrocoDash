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
| Horizontal grid (`Grid`) | `Grid(...)`, `Grid.from_supergrid(...)`, `Grid.subgrid_from_supergrid(...)`, `Grid.from_projection(...)` | `GridCreator` |
| Bathymetry (`Topo`) | `Topo(...)`, `Topo.from_topo_file(...)`, `Topo.set_from_dataset(...)`, `Topo.set_flat(...)` | `TopoEditor` |
| Vertical grid (`VGrid`) | `VGrid.uniform(...)`, `VGrid.hyperbolic(...)`, `VGrid.from_file(...)` | `VGridCreator` |

Notable features worth knowing about:

- **`TopoEditor`** — ipywidgets-based bathymetry editor with undo/redo,
  version-controlled edits, and live plotting. Great for fixing isolated
  basins, carving channels, or smoothing coastlines before case creation.
- **Version-controlled bathymetry** — `Topo` uses a per-domain `TopoLibrary/`
  directory under the hood. Every edit is committed as a git-style operation,
  so you can replay, share, or undo bathymetry changes reproducibly.
- **Curvilinear grids** — `Grid.from_supergrid(...)` works for both
  rectilinear (lon/lat) and curvilinear grids.
- **Polar domains** — `Grid.from_projection(...)` builds an Arctic or Antarctic
  grid on a polar stereographic projection.
- **ESMF mesh + SCRIP output** — the `Topo` object writes CICE grids, SCRIP
  grids, and ESMF meshes directly, which is what CESM needs for coupling.
- **runoff mapping helpers** — `mom6_forge.mapping` is used internally by
  `CrocoDash.forcing.runoff`, but is also available if you need it directly.

## Importing

The only difference from vanilla mom6_forge is the import path. Replace the
`mom6_forge` namespace with `CrocoDash`:

| Instead of... | Use... |
|---|---|
| `import mom6_forge.grid` | `import CrocoDash.grid` |
| `import mom6_forge.topo` | `import CrocoDash.topo` |
| `import mom6_forge.vgrid` | `import CrocoDash.vgrid` |

Everything else — class names, method signatures, parameters — is identical.

## API reference

The three grid classes and their widgets, as CrocoDash re-exports them. These
are mom6_forge's classes unchanged — this section exists because Sphinx does not
follow `import *` re-exports into the auto-generated
[API docs](../api-docs/CrocoDash.rst).

```{eval-rst}
.. autoclass:: CrocoDash.grid.Grid
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: CrocoDash.topo.Topo
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: CrocoDash.vgrid.VGrid
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: CrocoDash.grid_creator.GridCreator
   :members:
   :show-inheritance:

.. autoclass:: CrocoDash.topo_editor.TopoEditor
   :members:
   :show-inheritance:

.. autoclass:: CrocoDash.vgrid_creator.VGridCreator
   :members:
   :show-inheritance:
```

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
