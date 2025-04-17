import nbformat
import ast
import json


def load_workflow(json_file):
    with open(json_file, "r") as f:
        return json.load(f)


def extract_function_calls(code):
    """
    Extract names of all function calls from the given code string.
    Includes both regular function calls and method/attribute calls.
    """
    try:
        tree = ast.parse(code)
        function_names = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = get_full_func_name(node.func)
                if func_name:
                    function_names.add(func_name)
        return function_names
    except Exception as e:
        print(f"Error parsing code: {e}")
        return set()


def get_full_func_name(func_node):
    """
    Get the full dotted name of a function from an ast node.
    Handles simple calls (Grid), method calls (obj.func), and nested attributes (a.b.func).
    """
    parts = []
    while isinstance(func_node, ast.Attribute):
        parts.append(func_node.attr)
        func_node = func_node.value

    if isinstance(func_node, ast.Name):
        parts.append(func_node.id)
        return ".".join(reversed(parts))
    else:
        return None


def infer_outputs_from_functions(called_funcs, workflow_json):
    """Return a set of outputs based on which functions were called."""
    outputs = set()
    for step in workflow_json["steps"]:
        if step["function"] in called_funcs:
            outputs |= set(step["outputs"])
    return outputs


def get_all_called_functions(nb_path):
    nb = nbformat.read(nb_path, as_version=4)
    all_funcs = set()
    for cell in nb.cells:
        if cell.cell_type == "code":
            all_funcs |= extract_function_calls(cell.source)
    return all_funcs


def check_requirements(derived_outputs, workflow_json):
    required = set(workflow_json["requirements"]["mandatory"])
    missing = required - derived_outputs
    return missing


# ---- Run this ----
def validate_notebook(json_path, notebook_path):
    workflow = load_workflow(json_path)

    called_funcs = get_all_called_functions(notebook_path)
    derived_outputs = infer_outputs_from_functions(called_funcs, workflow)
    missing = check_requirements(derived_outputs, workflow)

    # print(f"Called functions: {called_funcs}")
    # print(f"Inferred outputs: {derived_outputs}")
    print(f"Missing requirements: {missing if missing else '✅ All good!'}")


def main():
    workflow = load_workflow(
        "/glade/u/home/manishrv/documents/croc/regional_mom_workflows/CrocoDash/docs/source/diagrams/workflow_diagram.json"
    )
    # visualize_workflow(workflow)
    validate_notebook(
        "/glade/u/home/manishrv/documents/croc/regional_mom_workflows/CrocoDash/docs/source/diagrams/workflow_diagram.json",
        "/glade/u/home/manishrv/documents/croc/regional_mom_workflows/CrocoDash/demos/minimal_demo_three_boundary.ipynb",
    )


if __name__ == "__main__":
    main()
