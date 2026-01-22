"""
This script setups all credentials and checks out CESM if needed.
"""

import os
import subprocess
import copernicusmarine
from pathlib import Path
import json
import sys

def main():

    path_file = Path(__file__).parent / "path_to_datasets_loc.json"
    if not path_file.is_file():
        path_file = Path(__file__).parent / "path_to_datasets.json"
    with open(path_file, "r") as f:
        paths = json.load(f)

    setup_glorys_credentials()
    setup_aws_credentials()
    if paths["CESM"] == "Checkout":
        checkout_cesm()


def setup_aws_credentials():
    """
    Set up the AWS credentials for accessing the S3 bucket.
    """
    aws_dir = Path(Path.home() / ".aws")
    aws_dir.mkdir(exist_ok=True)
    credentials_path = os.path.join(aws_dir, "credentials")
    aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    # Write to credentials file
    with open(credentials_path, "w") as f:
        f.write("[default]\n")
        f.write(f"aws_access_key_id = {aws_access_key_id}\n")
        f.write(f"aws_secret_access_key = {aws_secret_access_key}\n")
    print(f"Credentials written to {credentials_path}")
    return


def setup_glorys_credentials():
    """
    Set up the credentials for accessing the GLORYS data.
    """
    glorys_username = os.getenv("GLORYS_USERNAME")
    glorys_password = os.getenv("GLORYS_PASSWORD")

    if not copernicusmarine.login(check_credentials_valid=True):
        copernicusmarine.login(
            username=glorys_username, password=glorys_password, force_overwrite=True
        )


def checkout_cesm(
    repo_url="https://github.com/CROCODILE-CESM/CESM.git", checkout_dir="cesm"
):
    """
    Call a shell script to clone the CESM repo and run git-fleximod.
    """
    script_path = Path(__file__).parent / "helper_code" / "checkout_cesm.sh"
    try:
        subprocess.run([script_path, repo_url, checkout_dir], check=True)
    
            
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to set up CESM: {e}")

    set_cesm_path(str(Path(__file__).parent.parent / checkout_dir))



def set_cesm_path(cesm_path):
    
    data_path_in = Path(__file__).parent / "path_to_datasets.json"
    data_path_out = Path(__file__).parent / "path_to_datasets_loc.json"

    with open(data_path_in) as f:
        data = json.load(f)
    data["CESM"] = cesm_path
    with open(data_path_out, "w") as f:
        json.dump(data, f, indent=2)
if __name__ == "__main__":
    main()
