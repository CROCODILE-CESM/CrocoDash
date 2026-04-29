# User Guide

The CrocoDash workflow has four steps. Each step maps onto one module of the
package, so you can read the docs in the same order you'd actually run the code.

## The workflow at a glance

```text
  ┌──────────────────┐    ┌──────────────┐    ┌───────────────────────┐    ┌──────────────────────┐
  │  1.  Grids       │    │  2.  Case    │    │  3a. Configure        │    │  3b. Process         │
  │                  │    │      setup   │    │      forcings         │    │      forcings        │
  │  hgrid  (Grid)   │ →  │  Case(...)   │ →  │  case.configure_      │ →  │  case.process_       │
  │  topo   (Topo)   │    │              │    │    forcings(...)      │    │    forcings(...)     │
  │  vgrid  (VGrid)  │    │              │    │                       │    │                      │
  └──────────────────┘    └──────────────┘    └───────────────────────┘    └──────────────────────┘
       mom6_forge         visualCaseGen     forcing_configurations         extract_forcings
```

1. **[Grids](1_grids.md)** — build the horizontal grid, bathymetry, and vertical
   grid for your domain (using [mom6_forge](https://ncar.github.io/mom6_forge/)).
2. **[Case setup](2_case_setup.md)** — create a `Case` object that ties your
   grid to a CESM regional MOM6 case (using
   [VisualCaseGen](https://github.com/ESMCI/VisualCaseGen) under the hood).
3. **Forcings.** This step is split in two because the configuration is
   lightweight but the processing is HPC-scale:
   - **[3a. Configure forcings](3a_configure_forcings.md)** — declare which
     forcings your case needs (tides, BGC, runoff, …) and validate the choices.
   - **[3b. Process forcings](3b_process_forcings.md)** — run the extraction,
     regridding, and formatting. Submittable as a standalone batch job.

## Reference pages

These are not part of the linear workflow but you'll reach for them often:

- **[Compsets & Inputs](compsets_and_inputs.md)** — available CESM compsets, and how to customize MOM6 parameters via `user_nl_mom`.
- **[Datasets](datasets.md)** — which raw datasets CrocoDash can download, and how the `raw_data_access` registry works.
- **[Additional resources](additional_resources.md)** — talks, videos, and external tutorials.

```{toctree}
:caption: Workflow
:maxdepth: 1

1_grids
2_case_setup
3a_configure_forcings
3b_process_forcings
```

```{toctree}
:caption: Reference
:maxdepth: 1

compsets_and_inputs
datasets
additional_resources
```

## Frequently needed info

### "How do I set up a regional MOM6 case?"
Follow the four workflow pages in order, or see the [Tutorials & Gallery](https://crocodile-cesm.github.io/CrocoGallery/) for worked examples.

### "What compset should I use?"
See [Compsets & Inputs](compsets_and_inputs.md) for the aliases CrocoDash ships with.

### "What forcing options does my compset require?"
After you instantiate your `Case`, CrocoDash prints the required configurators.
You can also query the registry directly — see [Configure Forcings](3a_configure_forcings.md).

### "What raw datasets are available?"
See [Datasets](datasets.md).

### "How do I change a MOM6 input parameter?"
See the `user_nl_mom` section of [Compsets & Inputs](compsets_and_inputs.md).

### "Where are the working examples?"
[CrocoGallery](https://crocodile-cesm.github.io/CrocoGallery/) — notebooks and
end-to-end demos.

## Community & help

- **Issues:** [GitHub Issues](https://github.com/CROCODILE-CESM/CrocoDash/issues)
- **Questions & discussion:** [GitHub Discussions](https://github.com/CROCODILE-CESM/CrocoDash/discussions)
- **Common errors:** [discussion thread](https://github.com/CROCODILE-CESM/CrocoDash/discussions/84)
- **Want to extend CrocoDash?** See the [developer docs](../for_developers/index.md).
