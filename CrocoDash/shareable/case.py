from CrocoDash.case import *

def identify_non_standard_case_information(caseroot):

    # 1. Read in where to find CrocoDash init args
    identify_CrocoDashCase_init_args("Test")

    # 2. Read in where to find CrocoDash forcing_config args
    identify_CrocoDashCase_forcing_config_args("Test")
    

    # 3. Recreate the case

    # 4. Compare with original case
    diff_CESM_cases("Test1", "Test2")

    # 5. Find xmlchanges that aren't standard, Find user_nl changes that aren't standard

    # 6. Find files that aren't standard. 

    # 7. Print out all this information, and return as dict what needs to be added beyond CrocoDash information.

    pass

def identify_CrocoDashCase_init_args(caseroot):

    # 1. Read in where to find CrocoDash init args

    # 2. Return as dict

    pass

def identify_CrocoDashCase_forcing_config_args(caseroot):
    
    # 1. Read in where to find CrocoDash forcing_config args

    # 2. Return as dict

    pass

def diff_CESM_cases(caseroot_1, caseroot_2):

    # 1. Identify non-standard case information for both cases

    # 2. Compare the two cases' non-standard information

    # 3. Return the difference in xml files, Sourcemods, & user_nl files

    pass

def package_case_specific_info(caseroot):
    
    # 1. Call the identify function
    identify_non_standard_case_information(caseroot)

    # 2. Create a manifest file that lists all the changes, create a folder with all needed files

    # 3. Zip and return the path to the zip file

    pass

def read_from_case_package(zipfilepath):

    # 1. Read in the zip file, and manifest

    # 1.5 Modify the manifest file as wanted.
    modify_manifest("test")

    # 2. Return the dict of changes, and the files, create the CESM case
    given_manifest_info_create_case("test")

    pass

def given_manifest_info_create_case(manifest_dict):

    # 1. Read in the manifest dict

    # 2. Apply the changes to the case at caseroot

    pass

def modify_manifest(manifest_dict):

    # 1. Read in the manifest dict

    #2. Modify manifest as needed with FCR

    # 3. Return modified manifest

    pass

def share_from_case(caseroot):

    # 1. Identify non-standard case information

    # 2. Create manifest and folder with files

    # 3. Call modifiers

    # 4. Create Case

    pass