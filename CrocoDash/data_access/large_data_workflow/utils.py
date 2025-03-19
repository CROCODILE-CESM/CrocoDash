import json



def load_config(config_path: str = "config.json") -> dict:
    """
    Load a JSON config file.

    Parameters
    ----------
    config_path : str, optional
        Path to the JSON config file. Default is "config.json".

    Returns
    -------
    dict
        The loaded configuration as a dictionary.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_config(config: dict, config_path: str = "config.json") -> None:
    """
    Write or update a JSON config file.

    Parameters
    ----------
    config : dict
        Configuration dictionary to save.
    config_path : str, optional
        Path to the JSON config file. Default is "config.json".

    Returns
    -------
    None
    """
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, sort_keys=True)
    

