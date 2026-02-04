from visualCaseGen.custom_widget_types.case_tools import xmlchange, append_user_nl
import shutil
from pathlib import Path


def copy_xml_files_from_case(old_caseroot, new_caseroot, filenames):
    old_caseroot = Path(old_caseroot)
    new_caseroot = Path(new_caseroot)
    for name in filenames:
        shutil.copy(old_caseroot / name, new_caseroot / name)


def copy_user_nl_params_from_case(
    old_caseroot,
    usernlparams,
):
    for key in usernlparams:
        usernl = Path(old_caseroot) / f"user_nl_{key}"
        with usernl.open() as f:
            for line in f:
                line = line.strip()
                if line.startswith("!"):
                    continue

                # PARAM=VALUE
                param, value = line.split("=", 1)
                if param in usernlparams[key]:
                    append_user_nl(key, [(param.strip(), value.strip())])


def copy_source_mods_from_case(
    old_caseroot,
    new_caseroot,
    short_filepaths,
):
    old_caseroot = Path(old_caseroot)
    new_caseroot = Path(new_caseroot)
    for path in short_filepaths:
        path = Path(path)
        shutil.copy(
            old_caseroot / "SourceMods" / path, new_caseroot / "SourceMods" / path
        )


def apply_xmlchanges_to_case(
    old_caseroot,
    xmlchangeparams,
):
    # Copy old_caseroot replya.sh with that line on it and replay it verbatim with xmlchange()
    replay = Path(old_caseroot) / "replay.sh"
    with replay.open() as f:
        for line in f:
            line = line.strip()

            if not line.startswith("./xmlchange"):
                continue

            # ./xmlchange PARAM=VALUE
            _, kv = line.split(None, 1)
            param, value = kv.split("=", 1)
            if param in xmlchangeparams:
                xmlchange(param, value, is_non_local=True)


def copy_configurations_to_case(old_forcing_config, case, inputdir_ocnice):
    """
    Copy forcing configurations from inputdir_ocnice to case.inputdir/ocnice.
    """

    case_ocnice = case.inputdir / "ocnice"

    # Copy forcing_obc_seg* files
    for src in inputdir_ocnice.glob("forcing_obc_seg*"):
        if src.is_file():
            shutil.copy(src, case_ocnice)

    # Copy init_* files
    for src in inputdir_ocnice.glob("init_*"):
        if src.is_file():
            shutil.copy(src, case_ocnice)

    # Iterate through old_forcing_config outputs
    for key in old_forcing_config:
        if key == "basic" or key not in case.fcr.active_configurators.keys():
            continue
        for output in old_forcing_config[key].get("outputs", []):
            path = inputdir_ocnice / output
            if path.exists() and path.is_file():
                shutil.copy(path, case_ocnice)
