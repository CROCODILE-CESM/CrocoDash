from CrocoDash.data_access import glorys as gl
import pandas as pd


def test_glorys_pbs():
    gl.get_glorys_data_with_pbs(
        "/glade/u/home/manishrv/scratch/inputs_rm6/nwa_twenty_year/pbs_script_east.sh",
        "2000-01-01",
        "2020-12-31",
        lat_min=4.961175132990646,
        lat_max=58.61512088772785,
        lon_min=-37.68856021347937,
        lon_max=-36.093333333333256,
        output_dir="/glade/u/home/manishrv/scratch/inputs_rm6/nwa_twenty_year",
        boundary_name="east",
        mem=20,
        job_name = "glorys_east"
    )
    gl.get_glorys_data_with_pbs(
        "/glade/u/home/manishrv/scratch/inputs_rm6/nwa_twenty_year/pbs_script_south.sh",
        "2000-01-01",
        "2020-12-31",
        lat_min=4.961175132990646,
        lat_max=5.441175132990646,
        lon_min=-98.24,
        lon_max=-36.093333333333256,
        output_dir="/glade/u/home/manishrv/scratch/inputs_rm6/nwa_twenty_year",
        boundary_name="south",
        mem=20,
        job_name = "glorys_south"
    )
    gl.get_glorys_data_with_pbs(
        "/glade/u/home/manishrv/scratch/inputs_rm6/nwa_twenty_year/pbs_script_north.sh",
        "2000-01-01",
        "2020-12-31",
        lat_min=52.537190110517756,
        lat_max=58.61512088772785,
        lon_min=-98.98996846773888,
        lon_max=-37.208560213479366,
        output_dir="/glade/u/home/manishrv/scratch/inputs_rm6/nwa_twenty_year",
        boundary_name="north",
        mem=20,
        job_name = "glorys_north"
    )

    return


def test_get_glorys_data_from_rda():
    dates = ["2005-01-01", "2005-02-01"]
    lat_min = 30
    lat_max = 31
    lon_min = -71
    lon_max = -70
    dataset = gl.get_glorys_data_from_rda(
        pd.date_range(start=dates[0], end=dates[1]).to_pydatetime().tolist(),
        lat_min,
        lat_max,
        lon_min,
        lon_max,
    )
    print(dataset)


def test_get_glorys_data_from_api():
    dates = ["2000-01-01", "2020-12-31"]
    lat_min = 3
    lat_max = 61
    lon_min = -101
    lon_max = -34
    dataset = gl.get_glorys_data_from_cds_api(dates, lat_min, lat_max, lon_min, lon_max)
    dataset.to_netcdf("")
