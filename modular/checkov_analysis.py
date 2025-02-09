import json
from pathlib import Path
from cyclonedx.model.bom import Bom
from sqlalchemy.dialects.postgresql import insert, JSON
from modular.models import Dependency, Session
from packageurl import PackageURL
from sqlalchemy import String, Integer

def persist_dependencies(sbom_file: str, repo_id: int = 1) -> None:
    """
    Load an SBOM file, parse its components, and upsert them as dependencies
    into the database.

    :param sbom_file: The file path to the SBOM JSON file.
    :param repo_id: Identifier for the repository (default is 1).
    """
    path = Path(sbom_file)

    # Load the SBOM JSON file.
    try:
        with path.open('r') as f:
            sbom_json = json.load(f)
    except FileNotFoundError:
        print(f"Error: SBOM file '{sbom_file}' not found.")
        return
    except json.JSONDecodeError:
        print(f"Error: File '{sbom_file}' is not a valid JSON file.")
        return
    except Exception as e:
        print(f"Error reading SBOM file '{sbom_file}': {e}")
        return

    # Parse the SBOM using CycloneDX.
    try:
        bom = Bom.from_json(sbom_json)
    except Exception as e:
        print(f"Error parsing SBOM: {e}")
        return

    # Upsert each component from the SBOM as a dependency.
    with Session() as session:
        for component in bom.components:
            # Create a dictionary of property names and values for easy lookup.
            properties = {prop.name: prop.value for prop in component.properties}

            # Ensure that purl is stored as a string.
            purl_obj = getattr(component, "purl", None)
            purl_str = str(purl_obj) if purl_obj else None

            dep_data = {
                "repo_id": repo_id,
                "name": component.name,
                "version": component.version,
                "type": str(component.type) if component.type else None,
                "cpe": component.cpe,
                "purl": purl_str,
                "found_by": properties.get("syft:package:foundBy"),
                "language": properties.get("syft:package:language"),
                "package_type": properties.get("syft:package:type"),
                "metadata_type": properties.get("syft:package:metadataType"),
                "location": properties.get("syft:location"),
            }

            # Serialize any dict values
            dep_data = {k: json.dumps(v) if isinstance(v, dict) else v for k, v in dep_data.items()}

            stmt = insert(Dependency).values(
                repo_id=Integer(dep_data['repo_id']),
                name=String(dep_data['name']),
                version=String(dep_data['version']),
                type=String(dep_data['type']),
                cpe=String(dep_data['cpe']),
                purl=String(dep_data['purl']),
                found_by=String(dep_data['found_by']),
                language=String(dep_data['language']),
                package_type=String(dep_data['package_type']),
                metadata_type=String(dep_data['metadata_type']),
                location=JSON(dep_data['location'])
            ).on_conflict_do_update(
                index_elements=['repo_id', 'name', 'version'],
                set_={
                    "type": String(dep_data['type']),
                    "cpe": String(dep_data['cpe']),
                    "purl": String(dep_data['purl']),
                    "found_by": String(dep_data['found_by']),
                    "language": String(dep_data['language']),
                    "package_type": String(dep_data['package_type']),
                    "metadata_type": String(dep_data['metadata_type']),
                    "location": JSON(dep_data['location']),
                }
            )
            
            session.execute(stmt)

        try:
            session.commit()
            print("Successfully persisted dependencies to the database.")
        except Exception as e:
            session.rollback()
            print(f"Error committing dependencies: {e}")

def main():
    # Use the current working directory for the sbom.json file.
    sbom_file_path = Path.cwd() / "sbom.json"
    persist_dependencies(str(sbom_file_path))

if __name__ == '__main__':
    main()
