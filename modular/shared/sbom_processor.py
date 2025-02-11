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

    def persist_dependencies(self, sbom_file: str, repo_id: str) -> None:
        path = Path(sbom_file)

        self.logger.debug(f"Attempting to read SBOM file: {sbom_file}")
        try:
            with path.open('r', encoding="utf-8") as f:
                sbom_json = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
            self.logger.error(f"Error reading SBOM file '{sbom_file}': {e}")
            return

        self.logger.debug(f"Successfully loaded SBOM file.")

        try:
            bom = Bom.from_json(sbom_json)
            self.logger.debug(f"Successfully parsed SBOM. Found {len(bom.components)} components.")
        except Exception as e:
            self.logger.error(f"Error parsing SBOM: {e}")
            return

        session = Session()
        processed_count = 0
        try:
            for component in bom.components:
                properties = {prop.name: prop.value for prop in component.properties}
                purl_str = component.purl.to_string() if isinstance(component.purl, PackageURL) else str(component.purl) if component.purl else None

                version = component.version if component.version else "unknown"
                name = component.name if component.name else "unknown"
                ctype = component.type.name if component.type else None

                dep_data = {
                    "repo_id": repo_id,
                    "name": name,
                    "version": version,
                    "type": ctype,
                    "purl": purl_str,
                    "dependency_type": "resolved",
                    "found_by": properties.get("aquasecurity:trivy:Class"),
                    "package_type": properties.get("aquasecurity:trivy:PkgType"),
                }

                self.logger.debug(f"Processing component: {dep_data}")

                stmt = (
                    insert(Dependency)
                    .values(**dep_data)
                    .on_conflict_do_update(
                        index_elements=['repo_id', 'name', 'version'],
                        set_={
                            "type": dep_data["type"],
                            "purl": dep_data["purl"],
                            "dependency_type": dep_data["dependency_type"],
                        }
                    )
                )

                session.execute(stmt)
                processed_count += 1

            session.commit()
            self.logger.info(f"Successfully persisted {processed_count} components to the database.")

        except Exception as e:
            session.rollback()
            self.logger.error(f"Error committing dependencies: {e}")

        finally:
            session.close()

if __name__ == '__main__':
    sbom_file_path = Path.cwd() / "sbom.json"
    repo_id = "example_repo"
    processor = SBOMProcessor()
    processor.persist_dependencies(str(sbom_file_path), repo_id)