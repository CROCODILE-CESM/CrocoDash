from CrocoDash.extract_forcings import utils


def test_build_forcing_request_merges_function_args():
    product_info = {
        "u_var_name": "uo",
        "v_var_name": "vo",
        "eta_var_name": "zos",
        "tracer_var_names": {"temp": "thetao", "salt": "so"},
        "dataset_path": "/some/path",
    }

    variables, extra_args = utils.build_forcing_request(
        product_info, function_args={"member": 5}
    )

    assert extra_args["dataset_path"] == "/some/path"
    assert extra_args["member"] == 5
