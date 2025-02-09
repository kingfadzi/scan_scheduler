from cyclonedx.model.bom import Bom
from pathlib import Path
import json

def load_and_parse_sbom(file_path: Path) -> Bom | None:
    try:
        with file_path.open('r') as f:
            json_data = json.load(f)
        bom = Bom.from_json(json_data)
        return bom
    except FileNotFoundError:
        print(f"Error: '{file_path}' file not found.")
        return None
    except json.JSONDecodeError:
        print(f"Error: '{file_path}' is not a valid JSON file.")
        return None
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return None

def print_bom_contents(bom: Bom):
    print("SBOM Metadata:")
    if bom.metadata:
        serial_number = bom.metadata.serial_number if hasattr(bom.metadata, 'serial_number') else 'N/A'
        print(f"  Serial Number: {serial_number}")

    print("\nComponents:")
    for component in bom.components:
        print(f"  Name: {component.name}")
        print(f"  Version: {component.version}")
        print(f"  Type: {component.type.name if component.type else 'N/A'}")
        print(f"  CPE: {component.cpe if component.cpe else 'N/A'}")

        # Extract and print properties
        property_output = {}
        for prop in component.properties:
            property_output[prop.name] = prop.value

        # Display properties of interest if available
        print("  Properties:")
        for key in ['syft:package:foundBy', 'syft:package:language', 'syft:package:type', 'syft:package:metadataType', 'syft:location']:
            print(f"    {key}: {property_output.get(key, 'N/A')}")
        print("  ---")

def main():
    sbom_file_path = Path.cwd() / 'sbom.json'  # Load SBOM from the current working directory

    bom = load_and_parse_sbom(sbom_file_path)
    
    if bom:
        print_bom_contents(bom)
    else:
        print("Failed to process the SBOM.")

if __name__ == "__main__":
    main()