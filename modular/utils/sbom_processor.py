from cyclonedx.parser import BaseParser
from cyclonedx.model.bom import Bom

def parse_sbom(sbom_file_path):
    # Open and read the SBOM file
    with open(sbom_file_path, 'r') as sbom_file:
        sbom_contents = sbom_file.read()

    # Use the parser to parse the file content
    parser = BaseParser()
    return parser.parse(sbom_contents)

def deduplicate_components(bom):
    # Dictionary to hold unique components based on name and version
    unique_components = {}

    # Loop over each component in the BOM
    for component in bom.components:
        key = (component.name, component.version)
        if key not in unique_components:
            unique_components[key] = component

    return list(unique_components.values())

def main():
    sbom_file_path = 'sbom.json'  # Update this path to your SBOM file

    # Parse the SBOM
    bom = parse_sbom(sbom_file_path)

    # Deduplicate components
    unique_components = deduplicate_components(bom)

    # Print unique components and their properties
    for component in unique_components:
        print(f"Name: {component.name}, Version: {component.version}, Type: {component.type}")
        # Add any other properties you might need here

if __name__ == "__main__":
    main()