from datetime import datetime
import xarray as xr
from CrocoDash import utils
from CrocoDash.data_access.large_data_workflow.utils import (
    load_config,
    parse_dataset_folder,
)
from pathlib import Path
from collections import defaultdict

logger = utils.setup_logger(__name__)


def merge_piecewise_dataset(
    folder: str | Path,
    input_dataset_regex: str,
    date_format: str,
    start_date: str,
    end_date: str,
    boundary_number_conversion: dict,
    output_folder: str | Path,
):
    """ """
    logger.info("Parsing Regridded Data Folder")
    # Parse data folder and find required files
    start_date = datetime.strptime(start_date, date_format)
    end_date = datetime.strptime(end_date, date_format)
    boundary_file_list = parse_dataset_folder(folder, input_dataset_regex, date_format)
    inverted_bnc = {v: k for k, v in boundary_number_conversion.items()}
    boundary_list = boundary_file_list.keys()

    for seg_num in inverted_bnc:
        if f"{seg_num:03}" not in boundary_list:
            logger.error(
                f"Segment Number '{seg_num}' from boundary_number_conversion not found in the available boundary files. Did you correctly regrid the right boundaries? Change the boundary number conversion to match."
            )
            raise ValueError()

    matching_files = defaultdict(list)
    for boundary in boundary_list:
        for file_start, file_end, file_path in boundary_file_list[boundary]:
            if file_start <= end_date and file_end >= start_date:
                matching_files[boundary].append(file_path)

    # Merge Files
    logger.info("Merging Files")
    for boundary in boundary_list:
        ds = xr.open_mfdataset(
            matching_files[boundary],
            combine="nested",
            concat_dim="time",
            coords="minimal",
        )
        output_path = Path(output_folder) / f"forcing_obc_segment_{boundary}.nc"
        ds.to_netcdf(output_path)
        ds.close()
        logger.info(f"Saved {boundary} boundary at {output_path}")


def main(config_path):
    config = load_config(config_path)
    merge_piecewise_dataset(
        config["paths"]["raw_dataset_path"],
        config["raw_file_regex"]["regridded_dataset_pattern"],
        config["dates"]["format"],
        config["dates"]["start"],
        config["dates"]["end"],
        config["boundary_number_conversion"],
        config["paths"]["merged_dataset_path"],
    )
    return


if __name__ == "__main__":
    main(
        "/glade/u/home/manishrv/documents/croc/regional_mom_workflows/CrocoDash/CrocoDash/data_access/large_data_workflow/config.json"
    )
