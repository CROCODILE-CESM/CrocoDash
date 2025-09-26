import json
import inspect
import re
import subprocess
import sys
from pathlib import Path

import ipywidgets as widgets
from IPython.display import display, clear_output

from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid
from CrocoDash.case import Case

import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import numpy as np

class CaseAssembler:
    """
    Interactive widget for assembling a new Case from global Case Information.
    Decoupled from any current in-memory Case.
    """

    last_assembled_case = None
    last_selected_forcing_config = None
    _warned_vgrid_topo_depth = False

    @staticmethod
    def _just_filename(path):
        return Path(path).name if path else ""

    @staticmethod
    def _base_grid_name(fname):
        import re
        return re.sub(r'_[0-9a-f]{6}\.nc$', '.nc', fname)

    @staticmethod
    def assemble_case(caseroot, inputdir, cesmroot):
        """
        Launches an interactive widget to select grid/topo/vgrid/forcing config from global history,
        and assembles a new Case instance.
        """
        # --- Normalize Paths ---
        caseroot = Path(caseroot)
        inputdir = Path(inputdir)
        cesmroot = Path(cesmroot)
        history_path = caseroot / "case_information.json"

        if not history_path.exists():
            print("No global Case Information found.")
            return

        # --- Load Case Information ---
        with open(history_path, "r") as f:
            all_case_records = json.load(f)

        # --- Extract History Entries ---
        grid_hist, topo_hist, vgrid_hist = CaseAssembler._extract_history(all_case_records)

        # --- Reverse for most recent first ---
        grid_hist = list(reversed(grid_hist))
        topo_hist = list(reversed(topo_hist))
        vgrid_hist = list(reversed(vgrid_hist))
        
        # --- Build UI Widgets ---
        grid_dropdown, topo_dropdown, vgrid_dropdown, grid_hist, topo_hist, vgrid_hist = CaseAssembler._build_dropdowns(grid_hist, topo_hist, vgrid_hist)
        grid_preview, topo_preview, vgrid_preview = widgets.Output(), widgets.Output(), widgets.Output()

        # --- Forcing Configuration Section ---
        forcing_case_dropdown, forcing_config_output, case_forcing_map = CaseAssembler._build_forcing_section(all_case_records)

        # --- UI Layout Setup ---
        widgets_dict = CaseAssembler._build_ui_layout(
            grid_dropdown, topo_dropdown, vgrid_dropdown,
            grid_preview, topo_preview, vgrid_preview,
            forcing_case_dropdown
        )

        # --- Dropdown Observers ---
        grid_dropdown.observe(lambda change: CaseAssembler._update_grid_plot(change, grid_hist, grid_preview), names='value')
        topo_dropdown.observe(lambda change: CaseAssembler._update_topo_plot(change, grid_dropdown, topo_dropdown, grid_hist, topo_hist, topo_preview), names='value')
        vgrid_dropdown.observe(lambda change: CaseAssembler._update_vgrid_plot(change, vgrid_dropdown, vgrid_hist, vgrid_preview), names='value')
        forcing_case_dropdown.observe(lambda change: CaseAssembler._update_forcing_output(change, forcing_case_dropdown, case_forcing_map, forcing_config_output), names='value')

        # --- Initialize Preview ---
        CaseAssembler._update_grid_plot(None, grid_hist, grid_preview)
        CaseAssembler._update_topo_plot(None, grid_dropdown, topo_dropdown, grid_hist, topo_hist, topo_preview)
        CaseAssembler._update_vgrid_plot(None, vgrid_dropdown, vgrid_hist, vgrid_preview)

        # --- Topo Compatibility Observer ---
        def update_topo_options(*args):
            try:
                idx = int(grid_dropdown.value.split("]")[0][1:])
                grid_obj = Grid.from_netcdf(grid_hist[idx]["fullpath"])
                grid_obj.name = Case.clean_grid_name(grid_obj.name)
            except Exception:
                topo_dropdown.options = []
                return
            compatible_topos = [
                f"[{i}] {entry['file']} -- {entry['message']}"
                for i, entry in enumerate(topo_hist)
                if Case.topo_is_compatible_with_grid(entry["fullpath"], grid_obj)
            ]
            topo_dropdown.options = compatible_topos

        grid_dropdown.observe(lambda change: update_topo_options(), names='value')
        update_topo_options()

        # --- Assemble and Display UI ---
        display(widgets_dict["title"])
        display(widgets_dict["grid_box"])
        display(widgets_dict["topo_box"])
        display(widgets_dict["vgrid_box"])
        display(widgets_dict["forcing_box"])
        display(forcing_config_output)
        display(widgets_dict["casename_box"])
        display(widgets.HBox([widgets_dict["assemble_button"]]))
        display(widgets_dict["status_output"])

        # --- Assemble Button Logic ---
        widgets_dict["assemble_button"].on_click(
            lambda b: CaseAssembler._on_assemble_clicked(
                b, grid_dropdown, topo_dropdown, vgrid_dropdown,
                grid_hist, topo_hist, vgrid_hist,
                widgets_dict["casename_widget"], forcing_case_dropdown,
                case_forcing_map, caseroot, inputdir, cesmroot,
                widgets_dict["status_output"], widgets_dict["proceed_buttons"]
            )
        )

        widgets_dict["proceed_buttons"].observe(
            lambda change: CaseAssembler._on_proceed_change(change, widgets_dict["status_output"]),
            names='value'
        )


    # === History Parsing + Dropdown Builders ===
    @staticmethod
    def _extract_history(all_case_records):
        grid_seen, vgrid_seen, topo_seen = {}, {}, {}

        for idx, rec in enumerate(all_case_records):
            casename = Path(rec.get("caseroot", "")).name if rec.get("caseroot") else f"case_{idx}"
            for field, seen_dict in zip(["grid_file", "vgrid_file", "topo_file"], [grid_seen, vgrid_seen, topo_seen]):
                file = rec.get(field)
                if file and file != "unknown" and Path(file).exists():
                    fname = CaseAssembler._just_filename(file)
                    base = CaseAssembler._base_grid_name(fname)
                    key = (casename, base)
                    if key not in seen_dict or Path(file).stat().st_mtime > Path(seen_dict[key]["fullpath"]).stat().st_mtime:
                        seen_dict[key] = {
                            "file": fname,
                            "fullpath": file,
                            "message": f"From case '{casename}' (history idx {idx})"
                        }

        return list(grid_seen.values()), list(topo_seen.values()), list(vgrid_seen.values())

    @staticmethod
    def _build_dropdowns(grid_hist, topo_hist, vgrid_hist):
        def build_options(hist): return [f"[{i}] {e['file']} -- {e['message']}" for i, e in enumerate(hist)]
        grid_dropdown = widgets.Dropdown(options=build_options(grid_hist), layout=widgets.Layout(width='95%'))
        topo_dropdown = widgets.Dropdown(options=build_options(topo_hist), layout=widgets.Layout(width='95%'))
        vgrid_dropdown = widgets.Dropdown(options=build_options(vgrid_hist), layout=widgets.Layout(width='95%'))
        return grid_dropdown, topo_dropdown, vgrid_dropdown, grid_hist, topo_hist, vgrid_hist

    @staticmethod
    def _build_forcing_section(all_case_records):
        case_forcing_map = {}
        case_names = ["No Forcing Config [Default]"]
        idx_map = {}
        # Reverse to prioritize most recent
        for idx, rec in reversed(list(enumerate(all_case_records))):
            casename = Path(rec.get("caseroot", "")).name if rec.get("caseroot") else None
            if casename and casename not in case_forcing_map:
                case_forcing_map[casename] = rec.get("forcing_config", {})
                idx_map[casename] = idx
        # Build options with history idx
        for casename in case_forcing_map.keys():
            case_names.append(f"{casename} [history idx {idx_map[casename]}]")
        forcing_dropdown = widgets.Dropdown(
            options=case_names, value="No Forcing Config [Default]",
            layout=widgets.Layout(width='30%')
        )
        forcing_output = widgets.Output(layout={'border': '1px solid gray'})
        # Map dropdown value to config
        config_map = {"No Forcing Config [Default]": {}}
        for casename in case_forcing_map.keys():
            label = f"{casename} [history idx {idx_map[casename]}]"
            config_map[label] = case_forcing_map[casename]
        return forcing_dropdown, forcing_output, config_map

    @staticmethod
    def _build_ui_layout(grid_dd, topo_dd, vgrid_dd, grid_prev, topo_prev, vgrid_prev, forcing_dd):
        title = widgets.HTML("<h1>Case Assembler</h1>")
        grid_box = widgets.HBox([widgets.VBox([widgets.HTML("<h2>Grid File:</h2>"), grid_dd]), grid_prev])
        topo_box = widgets.HBox([widgets.VBox([widgets.HTML("<h2>Topo File:</h2>"), topo_dd]), topo_prev])
        vgrid_box = widgets.HBox([widgets.VBox([widgets.HTML("<h2>VGrid File:</h2>"), vgrid_dd]), vgrid_prev])
        forcing_box = widgets.VBox([widgets.HTML("<h2>Select Case for Forcing Config:</h2>"), forcing_dd])
        casename_widget = widgets.Text(value='', placeholder='Enter new casename (no spaces)', layout=widgets.Layout(width='30%'))
        casename_box = widgets.VBox([widgets.HTML("<h2>Case Name:</h2>"), casename_widget])
        assemble_button = widgets.Button(description="Assemble Case", button_style='success', layout=widgets.Layout(width='30%'))
        proceed_buttons = widgets.ToggleButtons(options=['Generate Forcings', 'Leave Case As-Is'], layout=widgets.Layout(width='100%'))
        status_output = widgets.Output()
        return {
            "title": title, "grid_box": grid_box, "topo_box": topo_box, "vgrid_box": vgrid_box,
            "forcing_box": forcing_box, "casename_widget": casename_widget, "casename_box": casename_box,
            "assemble_button": assemble_button,
            "proceed_buttons": proceed_buttons, "status_output": status_output
        }

    # === Preview Plot Functions ===
    @staticmethod
    def _update_grid_plot(change, grid_hist, output):
        with output:
            output.clear_output(wait=True)
            try:
                idx = int(change["new"].split("]")[0][1:]) if change else 0
                grid = Grid.from_netcdf(grid_hist[idx]["fullpath"])
                fig = plt.figure(figsize=(7, 6))
                ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
                ax.coastlines(resolution='10m', linewidth=1)
                ax.add_feature(cfeature.LAND, facecolor='0.9')
                for i in range(grid.qlon.shape[1]):
                    ax.plot(grid.qlon[:, i], grid.qlat[:, i], color='k', linewidth=0.1, transform=ccrs.PlateCarree())
                for j in range(grid.qlon.shape[0]):
                    ax.plot(grid.qlon[j, :], grid.qlat[j, :], color='k', linewidth=0.1, transform=ccrs.PlateCarree())
                ax.set_extent([float(grid.qlon.min()), float(grid.qlon.max()), float(grid.qlat.min()), float(grid.qlat.max())], crs=ccrs.PlateCarree())
                ax.set_title("Grid Preview")
                plt.show()
            except Exception as e:
                print("Failed to preview grid:", e)

    @staticmethod
    def _update_topo_plot(change, grid_dd, topo_dd, grid_hist, topo_hist, output):
        with output:
            output.clear_output(wait=True)
            try:
                grid_idx = int(grid_dd.value.split("]")[0][1:])
                topo_idx = int(topo_dd.value.split("]")[0][1:])
                grid = Grid.from_netcdf(grid_hist[grid_idx]["fullpath"])
                topo = Topo.from_topo_file(grid, topo_hist[topo_idx]["fullpath"])
                depth = np.where(getattr(topo, 'tmask', None) == 1, topo.depth, np.nan) if hasattr(topo, 'tmask') else np.where(topo.depth > 0, topo.depth, np.nan)
                fig, ax = plt.subplots(subplot_kw={'projection': ccrs.PlateCarree()}, figsize=(7, 6))
                im = ax.pcolormesh(grid.qlon, grid.qlat, depth, cmap='viridis', shading='auto')
                fig.colorbar(im, ax=ax, label='Depth (m)')
                ax.set_title("Topo Preview")
                ax.set_extent([grid.qlon.min(), grid.qlon.max(), grid.qlat.min(), grid.qlat.max()])
                plt.show()
            except Exception as e:
                print("Failed to preview topo:", e)

    @staticmethod
    def _update_vgrid_plot(change, vgrid_dd, vgrid_hist, output):
        with output:
            output.clear_output(wait=True)
            try:
                idx = int(vgrid_dd.value.split("]")[0][1:])
                vgrid = VGrid.from_file(vgrid_hist[idx]["fullpath"])
                fig, ax = plt.subplots(figsize=(7, 6))
                for depth in vgrid.z:
                    ax.axhline(y=depth, color='steelblue')
                ax.set_ylim(max(vgrid.z) + 10, min(vgrid.z) - 10)
                ax.set_ylabel("Depth (m)")
                ax.set_title("Vertical Grid Preview")
                plt.show()
            except Exception as e:
                print("Failed to preview vgrid:", e)

    @staticmethod
    def _update_forcing_output(change, dropdown, fmap, output):
        with output:
            output.clear_output()
            selected = change['new']
            config = fmap.get(selected, {})
            print(f"Forcing config for case '{selected}':" if config else "No forcing config available for this case.")
            if config:
                print(json.dumps(config, indent=2))

    # === Assemble and Proceed Handlers ===

    @staticmethod
    def _on_assemble_clicked(
        b, grid_dd, topo_dd, vgrid_dd,
        grid_hist, topo_hist, vgrid_hist,
        casename_widget, forcing_dropdown,
        forcing_map, caseroot, inputdir, cesmroot,
        status_output, proceed_buttons
    ):
        with status_output:
            clear_output()
            casename = casename_widget.value.strip()
            if " " in casename or casename == "":
                print("Case name cannot contain spaces and cannot be blank.")
                return

            # --- Load Grid ---
            try:
                idx = int(grid_dd.value.split("]")[0][1:])
                grid_path = grid_hist[idx]["fullpath"]
                grid_obj = Grid.from_netcdf(grid_path)
                grid_obj.name = Case.clean_grid_name(grid_obj.name)
            except Exception:
                print("Invalid grid selection.")
                return

            # --- Load Topo ---
            try:
                idx = int(topo_dd.value.split("]")[0][1:])
                topo_path = topo_hist[idx]["fullpath"]
                topo_obj = Topo.from_topo_file(grid_obj, topo_path)
            except Exception as e:
                print("WARNING: Selected Topo is not compatible with selected Grid (could not load Topo). Please remake your selections.")
                return

            # --- Load VGrid ---
            try:
                idx = int(vgrid_dd.value.split("]")[0][1:])
                vgrid_path = vgrid_hist[idx]["fullpath"]
                vgrid_obj = VGrid.from_file(vgrid_path)
            except Exception:
                print("Invalid vgrid selection.")
                return

            # --- Check VGrid vs Topo depth ---
            vgrid_depth = getattr(vgrid_obj, "depth", None)
            topo_max_depth = getattr(topo_obj, "max_depth", None)
            if vgrid_depth is not None and topo_max_depth is not None:
                if vgrid_depth < topo_max_depth - 0.5:
                    if not CaseAssembler._warned_vgrid_topo_depth:
                        print(f"WARNING: VGrid total depth ({vgrid_depth:.2f} m) is less than Topo max depth ({topo_max_depth:.2f} m)! If you click 'Assemble Case' again, the case will be assembled anyway.")
                        CaseAssembler._warned_vgrid_topo_depth = True
                        return
                    else:
                        print("WARNING: Proceeding with assembly despite VGrid/Topo depth mismatch.")

            # --- Forcing Config Selection ---
            selected_case = forcing_dropdown.value
            selected_forcing_config = forcing_map.get(selected_case, {}) if selected_case != "No Forcing Config [Default]" else {}

            # --- Create Case Object ---
            case_caseroot = caseroot / casename
            case_inputdir = inputdir / casename
            new_case = Case(
                cesmroot=cesmroot,
                caseroot=case_caseroot,
                inputdir=case_inputdir,
                ocn_grid=grid_obj,
                ocn_vgrid=vgrid_obj,
                ocn_topo=topo_obj,
                inittime="1850",
                datm_mode="JRA",
                datm_grid_name="TL319",
                ninst=1,
                machine="derecho",
                project="NCGD0011",  # <-- CHANGE AS NEEDED
                override=True,
                message="Assembled from per-object history",
                forcing_config=selected_forcing_config,
            )

            CaseAssembler.last_assembled_case = new_case
            CaseAssembler.last_selected_forcing_config = selected_forcing_config

            if selected_case != "No Forcing Config [Default]" and selected_forcing_config:
                proceed_buttons.value = None
                display(proceed_buttons)
            else:
                print("Case assembled. You can manually configure forcings later using case.configure_forcings().")

    @staticmethod
    def _on_proceed_change(change, status_output):
        with status_output:
            clear_output()
            if change['new'] == 'Generate Forcings':
                try:
                    new_case = CaseAssembler.last_assembled_case
                    selected_config = CaseAssembler.last_selected_forcing_config
                    if new_case is None or selected_config is None:
                        print("No case has been assembled yet. Please assemble a case first.")
                        return
                    valid_args = inspect.signature(new_case.configure_forcings).parameters
                    missing_args = [
                        k for k in valid_args
                        if k not in selected_config and valid_args[k].default is inspect._empty
                    ]
                    if missing_args:
                        print(f"Error: Forcing config is missing required arguments: {missing_args}")
                        print("Please select a valid forcing config or run configure_forcings manually.")
                        return
                    filtered_config = {k: v for k, v in selected_config.items() if k in valid_args}
                    print("Running configure_forcings...")
                    new_case.configure_forcings(**filtered_config)

                    glorys_dir = Path(new_case.inputdir) / "glorys"
                    script_path = glorys_dir / "get_glorys_data.sh"
                    if script_path.exists():
                        print("Executing GLORYS data download script. Progress will be shown below:")
                        try:
                            process = subprocess.Popen(
                                ["bash", str(script_path)],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True,
                                bufsize=1
                            )
                            last_reported = -1  # Start at -1 to catch 0%
                            for line in process.stdout:
                                if (
                                    "INFO" in line or
                                    "WARNING" in line or
                                    "ERROR" in line or
                                    line.strip().startswith("{") or
                                    line.strip().startswith("}")
                                ):
                                    print(line, end='')
                                    sys.stdout.flush()
                                else:
                                    match = re.match(r"\s*(\d+)%\|", line)
                                    if match:
                                        percent = int(match.group(1))
                                        if percent == 0 and last_reported < 0:
                                            print("Download progress: 0%")
                                            sys.stdout.flush()
                                            last_reported = 0
                                        elif percent >= last_reported + 25:
                                            print(f"Download progress: {percent}%")
                                            sys.stdout.flush()
                                            last_reported = percent - (percent % 25)
                                        elif percent == 100 and last_reported < 100:
                                            print("Download progress: 100%")
                                            sys.stdout.flush()
                                            last_reported = 100
                            process.wait()
                            if process.returncode == 0:
                                print("GLORYS data download complete.")
                            else:
                                print(f"ERROR: GLORYS script exited with code {process.returncode}")
                        except Exception as sub_err:
                            print(f"ERROR: Exception while executing {script_path}: {sub_err}")
                    else:
                        print("GLORYS script not found. Skipping script execution.")
                    print("Running process_forcings...")
                    new_case.process_forcings()
                    print("Forcings configured and processed.")
                except Exception as e:
                    print(f"Error during configure_forcings/process_forcings: {e}")
            elif change['new'] == 'Leave Case As-Is':
                print("Case left as-is. You can manually configure forcings later using case.configure_forcings().")
