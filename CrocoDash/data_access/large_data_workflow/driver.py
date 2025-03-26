import sys
import json
from pathlib import Path

sys.path.append("code")


def main():
    # Read in config
    workflow_dir = Path(__file__).parent
    config_path = workflow_dir / "config.json"
    with open(config_path, "r") as f:
        config = json.load(f)
    print("Config:", config)

    # Check step size makes sense
    if config["params"]["step"] <= 0:
        raise ValueError("step must be a positive integer.")
    # Call raw data getter

    # Call regrid data getter

    # Call data merger
    return


if __name__ == "__main__":
    main()
