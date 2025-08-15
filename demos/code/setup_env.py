"""
This script generates all raw data files required for the notebooks
"""

import os
import subprocess
import copernicusmarine
from pathlib import Path
import json

# Set the working directory to the location of this script
data_dir = Path(__file__).parent.parent / "data"


def main():

    with open(Path(__file__).parent / "data_paths.json", "r") as f:
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

    copernicusmarine.login(
        username=glorys_username, password=glorys_password, force_overwrite=True
    )


def checkout_cesm(
    repo_url="https://github.com/CROCODILE-CESM/CESM.git", checkout_dir="cesm"
):
    """
    Call a shell script to clone the CESM repo and run git-fleximod.
    """
    script_path = Path(__file__).parent / "checkout_cesm.sh"
    try:
        subprocess.run([script_path, repo_url, checkout_dir], check=True)
        subprocess.run(
            [
                "python",
                "set_cesm_path.py",
                str(Path(__file__).parent.parent / checkout_dir),
            ],
            cwd=Path(__file__).parent,  # sets the working directory for the subprocess
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to set up CESM: {e}")


if __name__ == "__main__":
    main()
