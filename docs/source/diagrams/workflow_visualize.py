import json
from graphviz import Digraph
from pathlib import Path

# Muted colors
MANDATORY_COLOR = "#66aa88"
OPTIONAL_COLOR = "#cc6666"


def load_workflow(json_file):
    with open(json_file, "r") as f:
        return json.load(f)


def visualize_workflow(workflow):
    # Track completed steps
    # Create a Graphviz directed graph
    # Build maps for fast lookup
    step_ids = {step["id"] for step in workflow["steps"]}
    output_to_step = {}
    all_outputs = set()

    dot = Digraph(format="png")

    step_style = {"shape": "box", "style": "filled", "color": "lightblue"}
    output_style = {"shape": "ellipse", "style": "filled", "color": "lightgray"}

    # Add step nodes and output nodes
    for step in workflow["steps"]:
        step_id = step["id"]
        step_label = f"{step['name']}\n[{step['function']}]"
        dot.node(step_id, step_label, **step_style)

        for out in step.get("outputs", []):
            all_outputs.add(out)
            output_to_step[out] = step_id
            dot.node(out, out, **output_style)
            dot.edge(step_id, out)  # Step → Output

    # Add dependency edges
    for step in workflow["steps"]:
        step_id = step["id"]
        for dep in step.get("dependencies", []):
            if dep in step_ids:
                dot.edge(dep, step_id)  # Step → Step
            elif dep in all_outputs:
                dot.edge(dep, step_id)  # Output → Step
            else:
                print(f"Warning: Unknown dependency '{dep}' for step '{step_id}'")
    # Draw requirements: mandatory (red), optional (green dashed)
    reqs = workflow.get("requirements", {})
    mandatory = set(reqs.get("mandatory", []))
    optional = set(reqs.get("optional", []))
    for output in mandatory:
        if output in all_outputs:
            dot.node(
                output, output, color=MANDATORY_COLOR, penwidth="2"
            )  # highlight border

    for output in optional:
        if output in all_outputs:
            dot.node(output, output, color=OPTIONAL_COLOR, penwidth="2")

    # Create the graph
    with dot.subgraph(name="cluster_legend") as legend:
        legend.attr(label="Legend", fontsize="12", style="rounded", color="gray")

        # Dummy nodes for legend
        legend.node(
            "mandatory_legend",
            "Mandatory Requirement",
            shape="oval",
            style="filled",
            color=MANDATORY_COLOR,
        )
        legend.node(
            "optional_legend",
            "Optional Requirement",
            shape="oval",
            style="filled",
            color=OPTIONAL_COLOR,
        )

        # Invisible edge to keep layout tidy
        legend.edge("mandatory_legend", "optional_legend", style="invis")
    # Render
    script_dir = Path(__file__).parent.parent  # Get the directory of the current script
    output_path = script_dir / "_static" / "workflow_diagram"
    dot.render(output_path)


def main():
    script_dir = Path(__file__).parent
    workflow = load_workflow(script_dir / "workflow_diagram.json")
    visualize_workflow(workflow)


if __name__ == "__main__":
    main()
