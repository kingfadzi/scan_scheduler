from cyclonedx.model import Component
from cyclonedx.parser import XmlParser, JsonParser
from cyclonedx.model.bom import Bom
from pathlib import Path

def load_and_parse_sbom(file_path):
    # Load and parse the JSON SBOM file
    try:
        with open(file_path, 'r') as f:
            sbom_contents = f.read()
        bom = Bom.from_text(sbom_contents, parser=JsonParser)
        return bom
    except FileNotFoundError:
        print(f"Error: '{file_path}' file not found.")
    except Exception as e:
        print(f"An error occurred while parsing the SBOM: {str(e)}")
    return None

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
    sbom_file_path = Path('sbom.json')  # Update this path to your SBOM file

    # Parse the SBOM
    bom = load_and_parse_sbom(sbom_file_path)
    
    if bom:
        # Deduplicate components
        unique_components = deduplicate_components(bom)

        # Print unique components and their properties
        for component in unique_components:
            print(f"Name: {component.name}, Version: {component.version}, Type: {component.type}")
    else:
        print("Failed to process the SBOM.")

if __name__ == "__main__":
    main()
