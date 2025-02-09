from cyclonedx.model.bom import Bom
from cyclonedx.parser import json as cdx_json
from pathlib import Path

def load_and_parse_sbom(file_path):
    # Load and parse the JSON SBOM file
    with open(file_path, 'r') as f:
        sbom_contents = f.read()
    parser = cdx_json.JsonParser(sbom_contents)
    bom = parser.parse()
    return bom

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
    sbom_file_path = Path('path_to_your_sbom.json')  # Update this path to your SBOM file

    # Parse the SBOM
    bom = load_and_parse_sbom(sbom_file_path)

    # Deduplicate components
    unique_components = deduplicate_components(bom)

    # Print unique components and their properties
    for component in unique_components:
        print(f"Name: {component.name}, Version: {component.version}, Type: {component.type}")

if __name__ == "__main__":
    main()
