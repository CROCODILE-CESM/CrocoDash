import os


def write_bash_curl_script(url, script_name, output_folder, output_filename):
    full_script_path = os.path.join(output_folder, script_name)
    full_path = os.path.join(output_folder, output_filename)
    script_lines = [
        "#!/bin/bash",
        "",
        f"mkdir -p {output_folder}",
        f"curl -L '{url}' -o '{full_path}'",
        'echo "Download complete."',
    ]

    with open(full_script_path, "w") as f:
        f.write("\n".join(script_lines))
    os.chmod(full_script_path, 0o755)  # Make it executable
    return full_script_path
