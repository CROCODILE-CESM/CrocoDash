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