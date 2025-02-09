from cyclonedx.model.bom import Bom
from pathlib import Path
import json

def load_and_parse_sbom(file_path: Path) -> Bom | None:
    try:
        with open(file_path, 'r') as f:
            json_data = json.load(f)
        bom = Bom.from_json(json_data)
        return bom
    except FileNotFoundError:
        print(f"Error: '{file_path}' file not found.")
    except json.JSONDecodeError:
        print(f"Error: '{file_path}' is not a valid JSON file.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    return None

def print_bom_contents(bom: Bom):
    print(f"SBOM Metadata:")
    print(f"  Version: {bom.version}")
    print(f"  Serial Number: {bom.serial_number}")

    # If bom.dependencies exists and has items
    if hasattr(bom, 'dependencies') and bom.dependencies:
        # Collect all references in dependencies
        direct_dependencies_refs = {dep.ref for dep in bom.dependencies}
    else:
        direct_dependencies_refs = set()

    print("\nComponents:")
    for component in bom.components:
        # Check if component's bom_ref is in direct_dependencies_refs
        dependency_type = "Direct" if component.bom_ref in direct_dependencies_refs else "Transient"
        print(f"  Name: {component.name}")
        print(f"  Version: {component.version}")
        print(f"  Type: {component.type}")
        print(f"  PURL: {component.purl}")
        print(f"  Dependency Type: {dependency_type}")
        print("  ---")

def main():
    sbom_file_path = Path('sbom.json')  # Update this path to your SBOM file

    bom = load_and_parse_sbom(sbom_file_path)
    
    if bom:
        print_bom_contents(bom)
    else:
        print("Failed to process the SBOM.")

if __name__ == "__main__":
    main()