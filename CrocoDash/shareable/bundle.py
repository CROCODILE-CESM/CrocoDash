import shutil
import json
from pathlib import Path
import zipfile
import os
from CrocoDash.forcing_configurations.base import *


def bundle_case_information(identify_output: dict, output_folder_location):
    """
    Copies all information into a subfolder and then zips it (returns location of the subfolder)
    """

    output_folder_location = Path(output_folder_location)
    differences = identify_output["differences"]
    caseroot = Path(identify_output["case_info"]["caseroot"])
    inputdir_ocnice = Path(identify_output["case_info"]["inputdir_ocnice"])

    case_subfolder = output_folder_location / f"{caseroot.name}_case_bundle"
    case_subfolder.mkdir(parents=True, exist_ok=True)

    # From caseroot, copy all user_nls
    for user_nl_file in caseroot.glob("user_nl_*"):
        shutil.copy(user_nl_file, case_subfolder / user_nl_file.name)

    # From caseroot, copy replay.sh
    replay_sh = caseroot / "replay.sh"
    shutil.copy(replay_sh, case_subfolder / "replay.sh")

    ## Copy Configuratorions
    # From inputdir, copy ocnice forcing_* and init_*
    ocnice_target = case_subfolder / "ocnice"
    ocnice_target.mkdir(parents=False, exist_ok=True)

    for f in inputdir_ocnice.iterdir():
        if f.name.startswith(("forcing_", "init_")):
            shutil.copy(f, ocnice_target)

    # We'll get the configurations and copy into bundle ocnice
    for config in identify_output["forcing_config"]:
        if config == "basic":
            continue
        # Deserialize

        configurator = ForcingConfigRegistry.get_configurator(
            identify_output["forcing_config"][config]
        )
        output_paths = configurator.get_output_filepaths(inputdir_ocnice)
        print(config, output_paths)
        for path in output_paths:
            shutil.copy(path, ocnice_target)

    # Write out identify_outputs
    with open(case_subfolder / "identify_output.json", "w") as f:
        json.dump(identify_output, f, indent=2, default=str)

    # From differences["xml_files"] and copy "sourceMods"
    xml_files_dir = case_subfolder / "xml_files"
    xml_files_dir.mkdir(exist_ok=True)
    for xml_file in differences["xml_files_missing_in_new"]:
        src = caseroot / xml_file
        if src.exists():
            shutil.copy(src, xml_files_dir / xml_file)

    # Copy sourceMods
    source_mods_orig = caseroot / "SourceMods"
    source_mods_dst = case_subfolder / "SourceMods"
    source_mods_dst.mkdir(exist_ok=True)
    for mod_file in differences["source_mods_missing_files"]:
        src = source_mods_orig / mod_file
        if src.exists():
            dst = source_mods_dst / mod_file
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)
    return case_subfolder


def compress_bundle(bundle_location):
    bundle_location = Path(bundle_location)
    zip_path = bundle_location / f"{caseroot.name}_case_bundle.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(bundle_location):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(bundle_location)
                zipf.write(file_path, arcname)

    return zip_path
