import json
from pathlib import Path
from cyclonedx.model.bom import Bom
from sqlalchemy.dialects.postgresql import insert
from packageurl import PackageURL
from modular.shared.models import Dependency, Session
from modular.shared.base_logger import BaseLogger
import logging

class SBOMProcessor(BaseLogger):
    def __init__(self):
        self.logger = self.get_logger("SBOMProcessor")
        self.logger.setLevel(logging.DEBUG)

    def persist_dependencies(self, sbom_file: str, repo_id: int = 1) -> None:

        path = Path(sbom_file)

        try:
            with path.open('r') as f:
                sbom_json = json.load(f)
        except FileNotFoundError:
            self.logger.error(f"Error: SBOM file '{sbom_file}' not found.")
            return
        except json.JSONDecodeError:
            self.logger.error(f"Error: File '{sbom_file}' is not a valid JSON file.")
            return
        except Exception as e:
            self.logger.error(f"Error reading SBOM file '{sbom_file}': {e}")
            return

        try:
            bom = Bom.from_json(sbom_json)
        except Exception as e:
            self.logger.error(f"Error parsing SBOM: {e}")
            return

        with Session() as session:
            for component in bom.components:
                properties = {prop.name: prop.value for prop in component.properties}

                purl_obj = getattr(component, "purl", None)
                purl_str = (
                    purl_obj.to_string() if isinstance(purl_obj, PackageURL)
                    else str(purl_obj) if purl_obj else None
                )

                if component.type:
                    if hasattr(component.type, "name"):
                        ctype = component.type.name
                    else:
                        ctype = str(component.type).replace("ComponentType.", "")
                else:
                    ctype = None

                dep_data = {
                    "repo_id": repo_id,
                    "name": component.name,
                    "version": component.version,
                    "type": ctype,
                    "cpe": component.cpe,
                    "purl": purl_str,
                    "found_by": properties.get("syft:package:foundBy"),
                    "language": properties.get("syft:package:language"),
                    "package_type": properties.get("syft:package:type"),
                    "metadata_type": properties.get("syft:package:metadataType"),
                    "location": properties.get("syft:location"),
                }

                stmt = (
                    insert(Dependency)
                    .values(**dep_data)
                    .on_conflict_do_update(
                        index_elements=['repo_id', 'name', 'version'],
                        set_={
                            "type": dep_data["type"],
                            "cpe": dep_data["cpe"],
                            "purl": dep_data["purl"],
                            "found_by": dep_data["found_by"],
                            "language": dep_data["language"],
                            "package_type": dep_data["package_type"],
                            "metadata_type": dep_data["metadata_type"],
                            "location": dep_data["location"],
                        }
                    )
                )
                session.execute(stmt)
            try:
                session.commit()
                self.logger.info("Successfully persisted dependencies to the database.")
            except Exception as e:
                session.rollback()
                self.logger.error(f"Error committing dependencies: {e}")

if __name__ == '__main__':

    sbom_file_path = Path.cwd() / "sbom.json"
    processor = SBOMProcessor()
    processor.persist_dependencies(str(sbom_file_path))
