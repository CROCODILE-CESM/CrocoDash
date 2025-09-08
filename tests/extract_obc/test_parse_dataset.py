from pathlib import Path
from CrocoDash.extract_obc.parse_dataset import parse_dataset


def test_parse_dataset(skip_if_not_glade, tmp_path, dummy_forcing_factory):

    ds = dummy_forcing_factory(
            36,
            56,
            36,
            56,
        )
    ds.to_netcdf(tmp_path  / "east.DOC.20200101.20200102.nc")
    ds.to_netcdf(tmp_path  / "west.DOC.20200101.20200102.nc")
    ds.to_netcdf(tmp_path  / "north.DIC.20200101.20200102.nc")
    ds.to_netcdf(tmp_path  / "south.DIC.20200101.20200102.nc")

    # Generate datasets

    vars = ["DIC", "DOC"]
    variable_info = parse_dataset(vars, tmp_path, "20200101", "20200131", regex = r"(\d{6,8}).(\d{6,8})")

    assert (str(tmp_path  / "north.DIC.20200101.20200102.nc") in variable_info["DIC"])
    assert (
        str(tmp_path  / "west.DOC.20200101.20200102.nc")
        in variable_info["DOC"]
    )
