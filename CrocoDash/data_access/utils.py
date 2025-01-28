def fill_template(template_path, output_path, **kwargs):
    """
    Reads a template file, fills it with the provided arguments, 
    and writes the filled content to a new file.
    
    Args:
        template_path (str): Path to the template file.
        output_path (str): Path to save the filled template.
        **kwargs: Key-value pairs for substitution in the template.
    """
    # Read the template file
    with open(template_path, 'r') as template_file:
        template_content = template_file.read()

    # Substitute placeholders with provided arguments
    filled_content = template_content.format(**kwargs)

    # Write the filled content to the output file
    with open(output_path, 'w') as output_file:
        output_file.write(filled_content)

    print(f"Filled PBS script written to: {output_path}")