import subprocess


def test_case_integration(get_CrocoDash_case):
    case = get_CrocoDash_case
    case.configure_forcings(
        date_range=["2020-01-01 00:00:00", "2020-02-01 00:00:00"],
        boundaries=["north", "south", "east"],
        too_much_data=True,
    )
    large_data_workflow_path = (
        case.inputdir / case.forcing_product_name / "large_data_workflow"
    )
    assert (large_data_workflow_path).exists()
    result = subprocess.run(
        ["python", large_data_workflow_path / "driver.py"],
        capture_output=True,
        text=True,
    )
    print(result.stdout)  # Output of the script
    assert result.returncode == 1 # Until PR is merged into LDW this is 1

    return
