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
    new_caseroot,
    usernlparams,
):
    pass


def copy_source_mods_from_case(
    old_caseroot,
    new_caseroot,
    filepaths,
):
    old_caseroot = Path(old_caseroot)
    new_caseroot = Path(new_caseroot)
    for path in filepaths:
        path = Path(path)
        shutil.copy(
            old_caseroot / "SourceMods" / name, new_caseroot / "SourceMods" / name
        )


def apply_xmlchanges_to_case(
    case,
    xmlchangeparams,
):
    pass


def copy_configurations_to_case(old_forcing_config, case, old_inputdir):

    # Copy forcing_obc_seg*
    shutil.copy(old_inputdir / "ocnice" / "forcing_obc_seg*", case.inputdir / "ocnice")
    # Copy init_*
    shutil.copy(old_inputdir / "ocnice" / "init_*", case.inputdir / "ocnice")

    # Interate through outputs
    for key in forcing_config:
        if key == "basic" or key not in case.fcr.active_configurators.keys():
            continue
        for output in forcing_config[key]["outputs"]:
            path = inputdir / "ocnice" / output
            if path.exists():
                shutil.copy(path, case.inputdir / "ocnice")
    pass
