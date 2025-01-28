#!/bin/bash -l
#PBS -N {job_name}
#PBS -A {project}
#PBS -l select=1:ncpus={ncpus}:mem={mem}gb
#PBS -l walltime={walltime}
#PBS -q {queue}
#PBS -m abe


BOUNDARY_NAME="{boundary_name}"
START_DATE="{start_date}"
END_DATE="{end_date}"
LON_MIN={lon_min}
LON_MAX={lon_max}
LAT_MIN={lat_min}
LAT_MAX={lat_max}
OUTPUT_DIR={output_dir}

mamba activate {env_name}

python {script_path}   \
    --state_file_boundary_name $BOUNDARY_NAME \
    --start_date $START_DATE \
    --end_date $END_DATE \
    --lon_min $LON_MIN \
    --lon_max $LON_MAX \
    --lat_min $LAT_MIN \
    --lat_max $LAT_MAX \
    --output_dir $OUTPUT_DIR


