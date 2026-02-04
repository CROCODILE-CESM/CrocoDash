import shutil
import json
from pathlib import Path
import zipfile
import os


def bundle_case_information(identify_output: dict, output_folder_location):
    """
    Copies all information into a subfolder and then zips it (returns location of the subfolder)
    """

    output_folder_location = Path(output_folder_location)
    differences = identify_output["differences"]
    caseroot = Path(identify_output["case_info"]["caseroot"])
    inputdir = Path(identify_output["case_info"]["inputdir"])

    case_subfolder = output_folder_location / f"{caseroot.name}_case_bundle"
    case_subfolder.mkdir(parents=True, exist_ok=True)

    # From caseroot, copy all user_nls
    for user_nl_file in caseroot.glob("user_nl_*"):
        shutil.copy(user_nl_file, case_subfolder / user_nl_file.name)

    # From caseroot, copy replay.sh
    replay_sh = caseroot / "replay.sh"
    shutil.copy(replay_sh, case_subfolder / "replay.sh")

    # From inputdir, copy ocnice
    ocnice_dir = inputdir / "ocnice"
    if ocnice_dir.exists():
        shutil.copytree(ocnice_dir, case_subfolder / "ocnice", dirs_exist_ok=True)

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

    # Zip the folder and place a copy at the same level as the case subfolder
    zip_path = case_subfolder / f"{caseroot.name}_case_bundle.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(case_subfolder):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(case_subfolder)
                zipf.write(file_path, arcname)

    return case_subfolder
