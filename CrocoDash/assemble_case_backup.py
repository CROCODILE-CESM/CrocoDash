import ipywidgets as widgets
from IPython.display import display, clear_output
from pathlib import Path
import json
import inspect

from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid
from CrocoDash.case import Case  # Used only to instantiate new cases and utility methods

class CaseAssembler:
    """
    Interactive widget for assembling a new Case from global case history.
    Decoupled from any current in-memory Case.
    """

    @staticmethod
    def assemble_case(caseroot, inputdir, cesmroot):
        """
        Launches an interactive widget to select grid/topo/vgrid/forcing config from global history,
        and builds a new Case instance.

        Args:
            caseroot (str or Path): Parent directory containing all cases and history files
            inputdir (str or Path): Parent directory for new input dirs
            cesmroot (str or Path): CESM root directory

        Returns:
            None (displays widget; stores last_built_case as attribute)
        """
        caseroot = Path(caseroot)
        inputdir = Path(inputdir)
        cesmroot = Path(cesmroot)

        history_path = caseroot / "case_history.json"

        # --- Load global case history ---
        if not history_path.exists():
            print("No global case history found.")
            return

        with open(history_path, "r") as f:
            all_case_records = json.load(f)

        # --- Helper functions ---
        def just_filename(path):
            return Path(path).name if path else ""

        def base_grid_name(fname):
            import re
            return re.sub(r'_[0-9a-f]{6}\.nc$', '.nc', fname)

        # --- Build dropdown options from history ---
        grid_hist, vgrid_hist, topo_hist = [], [], []
        grid_seen, vgrid_seen, topo_seen = {}, {}, {}

        for idx, rec in enumerate(all_case_records):
            casename = Path(rec.get("caseroot", "")).name if rec.get("caseroot") else f"case_{idx}"
            grid_file = rec.get("grid_file", None)
            vgrid_file = rec.get("vgrid_file", None)
            topo_file = rec.get("topo_file", None)

            if grid_file and grid_file != "unknown":
                fname = just_filename(grid_file)
                base = base_grid_name(fname)
                key = (casename, base)
                grid_path = Path(grid_file)
                if grid_path.exists():
                    if key not in grid_seen or grid_path.stat().st_mtime > Path(grid_seen[key]["fullpath"]).stat().st_mtime:
                        grid_seen[key] = {
                            "file": fname,
                            "fullpath": grid_file,
                            "message": f"From case '{casename}' (history idx {idx})"
                        }
            if vgrid_file and vgrid_file != "unknown":
                fname = just_filename(vgrid_file)
                base = base_grid_name(fname)
                key = (casename, base)
                vgrid_path = Path(vgrid_file)
                if vgrid_path.exists():
                    if key not in vgrid_seen or vgrid_path.stat().st_mtime > Path(vgrid_seen[key]["fullpath"]).stat().st_mtime:
                        vgrid_seen[key] = {
                            "file": fname,
                            "fullpath": vgrid_file,
                            "message": f"From case '{casename}' (history idx {idx})"
                        }
            if topo_file and topo_file != "unknown":
                fname = just_filename(topo_file)
                base = base_grid_name(fname)
                key = (casename, base)
                topo_path = Path(topo_file)
                if topo_path.exists():
                    if key not in topo_seen or topo_path.stat().st_mtime > Path(topo_seen[key]["fullpath"]).stat().st_mtime:
                        topo_seen[key] = {
                            "file": fname,
                            "fullpath": topo_file,
                            "message": f"From case '{casename}' (history idx {idx})"
                        }

        grid_hist = list(grid_seen.values())
        vgrid_hist = list(vgrid_seen.values())
        topo_hist = list(topo_seen.values())

        grid_options = [f"[{i}] {entry['file']} -- {entry['message']}" for i, entry in enumerate(grid_hist)]
        vgrid_options = [f"[{i}] {entry['file']} -- {entry['message']}" for i, entry in enumerate(vgrid_hist)]
        topo_options = [f"[{i}] {entry['file']} -- {entry['message']}" for i, entry in enumerate(topo_hist)]

        grid_dropdown = widgets.Dropdown(
            options=grid_options,
            style={'description_width': 'initial'},
            layout=widgets.Layout(width='80%')
        )
        topo_dropdown = widgets.Dropdown(
            options=topo_options,
            style={'description_width': 'initial'},
            layout=widgets.Layout(width='80%')
        )
        vgrid_dropdown = widgets.Dropdown(
            options=vgrid_options,
            style={'description_width': 'initial'},
            layout=widgets.Layout(width='80%')
        )

        grid_preview = widgets.Output()
        topo_preview = widgets.Output()
        vgrid_preview = widgets.Output()

        # --- Forcing config selection ---
        case_forcing_map = {}
        for rec in reversed(all_case_records):
            casename = Path(rec.get("caseroot", "")).name if rec.get("caseroot") else None
            if casename and casename not in case_forcing_map:
                case_forcing_map[casename] = rec.get("forcing_config", {})
        case_names = ["No Forcing Config [Default]"] + [name for name in case_forcing_map.keys() if name is not None]
        forcing_case_dropdown = widgets.Dropdown(
            options=case_names,
            value="No Forcing Config [Default]", 
            style={'description_width': 'initial'},
            layout=widgets.Layout(width='80%')
        )

        forcing_config_output = widgets.Output(layout={'border': '1px solid gray'})

        # Add header-style labels above each dropdown
        grid_header = widgets.HTML("<h2>Grid File:</h2>")
        topo_header = widgets.HTML("<h2>Topo File:</h2>")
        vgrid_header = widgets.HTML("<h2>VGrid File:</h2>")
        forcing_header = widgets.HTML("<h2>Select Case for Forcing Config:</h2>")

        # Topo preview box: Topo header + Topo dropdown + Topo plot side by side
        topo_box = widgets.HBox([
            widgets.VBox([topo_header, topo_dropdown]),
            widgets.VBox([topo_preview])
        ])

        # Grid preview box: Grid header + Grid dropdown + Grid plot side by side
        grid_box = widgets.HBox([
            widgets.VBox([grid_header, grid_dropdown]),
            widgets.VBox([grid_preview])
        ])

        # VGrid preview box: VGrid header + VGrid dropdown + VGrid plot side by side
        vgrid_box = widgets.HBox([
            widgets.VBox([vgrid_header, vgrid_dropdown]),
            widgets.VBox([vgrid_preview])
        ])

        # Forcing config selection: header + dropdown
        forcing_box = widgets.VBox([forcing_header, forcing_case_dropdown])

        # --- INSERT THE PREVIEW CODE SNIPPET HERE ---

        import matplotlib.pyplot as plt
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature

        def update_grid_plot(change=None):
            with grid_preview:
                grid_preview.clear_output(wait=True)
                try:
                    # Get selected index from dropdown
                    grid_sel = grid_dropdown.value
                    idx = int(grid_sel.split("]")[0][1:])
                    grid_obj = Grid.from_netcdf(grid_hist[idx]["fullpath"])
                    fig = plt.figure(figsize=(7, 6))
                    ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
                    ax.coastlines(resolution='10m', linewidth=1)
                    ax.add_feature(cfeature.LAND, facecolor='0.9')
                    ax.add_feature(cfeature.BORDERS, linewidth=0.5)

                    n_jq, n_iq = grid_obj.qlon.shape
                    for i in range(n_iq):
                        ax.plot(grid_obj.qlon[:, i], grid_obj.qlat[:, i], color='k', linewidth=0.1, transform=ccrs.PlateCarree())
                    for j in range(n_jq):
                        ax.plot(grid_obj.qlon[j, :], grid_obj.qlat[j, :], color='k', linewidth=0.1, transform=ccrs.PlateCarree())
                    ax.set_title("Grid Preview")

                    lon_min, lon_max = float(grid_obj.qlon.min()), float(grid_obj.qlon.max())
                    lat_min, lat_max = float(grid_obj.qlat.min()), float(grid_obj.qlat.max())
                    ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())

                    gl = ax.gridlines(draw_labels=True, linewidth=0, color='none')
                    gl.top_labels = False
                    gl.right_labels = False
                    gl.xlabel_style = {'size': 10}
                    gl.ylabel_style = {'size': 10}

                    plt.show()
                except Exception as e:
                    print("Failed to preview grid:", e)

        # Initial Grid plot
        update_grid_plot()

        # Attach observer for dynamic updates
        grid_dropdown.observe(update_grid_plot, names='value')

        def update_topo_plot(change=None):
            with topo_preview:
                topo_preview.clear_output(wait=True)
                try:
                    import numpy as np
                    # Get selected index from dropdown
                    topo_sel = topo_dropdown.value
                    if not topo_sel:
                        print("No compatible topo selected.")
                        return
                    idx = int(topo_sel.split("]")[0][1:])
                    # Use the currently selected grid as well
                    grid_sel = grid_dropdown.value
                    grid_idx = int(grid_sel.split("]")[0][1:])
                    grid_obj = Grid.from_netcdf(grid_hist[grid_idx]["fullpath"])
                    topo_obj = Topo.from_topo_file(grid_obj, topo_hist[idx]["fullpath"])
                    depth = np.array(topo_obj.depth)
                    # Mask land points (if tmask exists, mask where tmask==0)
                    if hasattr(topo_obj, 'tmask'):
                        depth = np.where(topo_obj.tmask == 1, depth, np.nan)
                    else:
                        depth = np.where(depth > 0, depth, np.nan)
                    cmap = plt.get_cmap('viridis').copy()
                    cmap.set_bad('white')
                    fig = plt.figure(figsize=(7, 6))
                    ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
                    # Do NOT add land or borders!
                    im = ax.pcolormesh(
                        grid_obj.qlon,
                        grid_obj.qlat,
                        depth,
                        cmap=cmap,
                        shading='auto',
                        transform=ccrs.PlateCarree()
                    )
                    fig.colorbar(im, ax=ax, orientation='vertical', pad=0.02, label='Depth (m)')
                    ax.set_title("Topo Preview")
                    lon_min, lon_max = float(grid_obj.qlon.min()), float(grid_obj.qlon.max())
                    lat_min, lat_max = float(grid_obj.qlat.min()), float(grid_obj.qlat.max())
                    ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())
                    gl = ax.gridlines(draw_labels=True, linewidth=0, color='none')
                    gl.top_labels = False
                    gl.right_labels = False
                    gl.xlabel_style = {'size': 10}
                    gl.ylabel_style = {'size': 10}
                    plt.show()
                except Exception as e:
                    print("Failed to preview topo:", e)

        # Initial Topo plot
        update_topo_plot()

        def update_vgrid_plot(change=None):
            with vgrid_preview:
                vgrid_preview.clear_output(wait=True)
                try:
                    idx = int(vgrid_dropdown.value.split("]")[0][1:])
                    vgrid_obj = VGrid.from_file(vgrid_hist[idx]["fullpath"])
                    import numpy as np
                    import matplotlib.pyplot as plt
                    fig, ax = plt.subplots(figsize=(7, 6))
                    for depth in vgrid_obj.z:
                        ax.axhline(y=depth, color='steelblue')
                    ax.set_ylim(max(vgrid_obj.z) + 10, min(vgrid_obj.z) - 10)
                    ax.set_ylabel("Depth (m)")
                    ax.set_title("Vertical Grid Preview")
                    plt.show()
                except Exception as e:
                    print("Failed to preview vgrid:", e)

        # Initial VGrid plot
        update_vgrid_plot()

        def on_forcing_case_change(change):
            with forcing_config_output:
                forcing_config_output.clear_output()
                selected_case = change['new']
                config = case_forcing_map.get(selected_case, {})
                if config:
                    print(f"Forcing config for case '{selected_case}':")
                    print(json.dumps(config, indent=2))
                else:
                    print("No forcing config available for this case.")

        forcing_case_dropdown.observe(on_forcing_case_change, names='value')

        casename_header = widgets.HTML("<h2>Case Name:</h2>")
        casename_widget = widgets.Text(
            value='',
            placeholder='Enter new casename (no spaces)',
            # description='Case name:',  # REMOVE THIS LINE
            style={'description_width': 'initial'},
            layout=widgets.Layout(width='50%')
        )
        proceed_buttons = widgets.ToggleButtons(
            options=['Generate Forcings', 'Leave Case As-Is'],
            description='Next step:',
            style={'description_width': 'initial'},
            layout=widgets.Layout(width='100%')
        )
        build_button = widgets.Button(description="Build Case", button_style='success')
        cancel_button = widgets.Button(description="Cancel", button_style='danger')
        status_output = widgets.Output()

        # --- Helper to update Topo dropdown based on selected Grid ---
        def update_topo_options(*args):
            grid_sel = grid_dropdown.value
            try:
                idx = int(grid_sel.split("]")[0][1:])
                grid_path = grid_hist[idx]["fullpath"]
                grid_obj = Grid.from_netcdf(grid_path)
                grid_obj.filename = grid_path  
                grid_obj.name = Case.clean_grid_name(grid_obj.name)
            except Exception as e:
                topo_dropdown.options = []
                return

            compatible_topos = []
            for i, entry in enumerate(topo_hist):
                topo_path = entry["fullpath"]
                is_compatible = Case.topo_is_compatible_with_grid(topo_path, grid_obj)
                if is_compatible:
                    compatible_topos.append(f"[{i}] {entry['file']} -- {entry['message']}")
            topo_dropdown.options = compatible_topos

        # Attach observer for dynamic updates
        topo_dropdown.observe(update_topo_plot, names='value')
        grid_dropdown.observe(update_topo_plot, names='value')
        vgrid_dropdown.observe(update_vgrid_plot, names='value')

        # Attach the observer to the grid dropdown
        grid_dropdown.observe(lambda change: update_topo_options(), names='value')

        # Initialize Topo dropdown for the initial Grid selection
        update_topo_options()

        title_header = widgets.HTML("<h1>Case Assembler</h1>")

        display(title_header)
        display(grid_box)
        display(topo_box)
        display(vgrid_box)
        display(forcing_box)
        display(forcing_config_output)
        display(widgets.VBox([casename_header, casename_widget]))
        display(widgets.HBox([build_button, cancel_button]))
        display(status_output)

        # --- Internal state for widget ---
        CaseAssembler.last_built_case = None
        CaseAssembler.last_selected_forcing_config = None
        CaseAssembler._warned_vgrid_topo_depth = False
        
        def on_build_clicked(b):
            with status_output:
                clear_output()
                casename = casename_widget.value.strip()
                if " " in casename or casename == "":
                    print("Case name cannot contain spaces and cannot be blank.")
                    return
                # Grid
                grid_sel = grid_dropdown.value
                try:
                    idx = int(grid_sel.split("]")[0][1:])
                    file_path = grid_hist[idx]["fullpath"]
                    grid_obj = Grid.from_netcdf(file_path)
                    grid_obj.name = Case.clean_grid_name(grid_obj.name)
                except Exception:
                    print("Invalid grid selection.")
                    return
                # Topo
                topo_sel = topo_dropdown.value
                try:
                    idx = int(topo_sel.split("]")[0][1:])
                    file_path = topo_hist[idx]["fullpath"]
                    topo_obj = Topo.from_topo_file(grid_obj, file_path)
                except Exception as e:
                    print("WARNING: Selected Topo is not compatible with selected Grid (could not load Topo). Please remake your selections.")
                    return
                # VGrid
                vgrid_sel = vgrid_dropdown.value
                try:
                    idx = int(vgrid_sel.split("]")[0][1:])
                    file_path = vgrid_hist[idx]["fullpath"]
                    vgrid_obj = VGrid.from_file(file_path)
                except Exception:
                    print("Invalid vgrid selection.")
                    return
                # --- VGrid/Topo depth check ---
                vgrid_depth = getattr(vgrid_obj, "depth", None)
                topo_max_depth = getattr(topo_obj, "max_depth", None)
                if vgrid_depth is not None and topo_max_depth is not None:
                    if vgrid_depth < topo_max_depth - 0.5:
                        if not CaseAssembler._warned_vgrid_topo_depth:
                            print(f"WARNING: VGrid total depth ({vgrid_depth:.2f} m) is less than Topo max depth ({topo_max_depth:.2f} m)! If you click 'Build Case' again, the case will be built anyway.")
                            CaseAssembler._warned_vgrid_topo_depth = True
                            return
                        else:
                            print("WARNING: Proceeding with build despite VGrid/Topo depth mismatch.")

                selected_case = forcing_case_dropdown.value
                selected_forcing_config = case_forcing_map.get(selected_case, {}) if selected_case != "No Forcing Config [Default]" else {}

                case_caseroot = caseroot / casename
                case_inputdir = inputdir / casename

                new_case = Case(
                    cesmroot=cesmroot,
                    caseroot=case_caseroot,
                    inputdir=case_inputdir,
                    ocn_grid=grid_obj,
                    ocn_vgrid=vgrid_obj,
                    ocn_topo=topo_obj,
                    inittime="1850",  # or get from UI/history if desired
                    datm_mode="JRA",  # or get from UI/history if desired
                    datm_grid_name="TL319",  # or get from UI/history if desired
                    ninst=1,
                    machine="derecho",
                    project="NCGD0011", # <-- CHANGE AS NEEDED
                    override=True,
                    message="Built from per-object history",
                    forcing_config=selected_forcing_config,
                )

                CaseAssembler.last_built_case = new_case
                CaseAssembler.last_selected_forcing_config = selected_forcing_config

                # If a valid forcing config is selected, show proceed_buttons for user choice
                if selected_case != "No Forcing Config [Default]" and selected_forcing_config:
                    proceed_buttons.value = None  # <-- Reset selection so observer fires
                    display(proceed_buttons)
                    proceed_buttons.observe(on_proceed_change, names='value')
                else:
                    print("Case built. You can manually configure forcings later using case.configure_forcings().")

        build_button.on_click(on_build_clicked)

        def on_cancel_clicked(b):
            with status_output:
                clear_output()
                print("Case build cancelled by user.")

        cancel_button.on_click(on_cancel_clicked)

        def on_proceed_change(change):
            with status_output:
                clear_output()
                if change['new'] == 'Generate Forcings':
                    try:
                        new_case = CaseAssembler.last_built_case
                        selected_forcing_config = CaseAssembler.last_selected_forcing_config
                        if new_case is None or selected_forcing_config is None:
                            print("No case has been built yet. Please build a case first.")
                            return
                        valid_args = inspect.signature(new_case.configure_forcings).parameters
                        missing_args = [k for k in valid_args if k not in selected_forcing_config and valid_args[k].default is inspect._empty]
                        if missing_args:
                            print(f"Error: Forcing config is missing required arguments: {missing_args}")
                            print("Please select a valid forcing config or run configure_forcings manually.")
                            return
                        filtered_config = {k: v for k, v in selected_forcing_config.items() if k in valid_args}
                        new_case.configure_forcings(**filtered_config)
                        new_case.process_forcings()
                        print("Forcings configured and processed.")
                    except Exception as e:
                        print(f"Error during configure_forcings/process_forcings: {e}")
                elif change['new'] == 'Leave Case As-Is':
                    print("Case left as-is. You can manually configure forcings later using case.configure_forcings().")
                    