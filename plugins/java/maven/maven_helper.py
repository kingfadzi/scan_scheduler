from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
import logging
from typing import List, Dict, Set
from shared.base_logger import BaseLogger
from shared.models import Dependency
from config.config import Config


class MavenHelper(BaseLogger):
    EXCLUDE_DIRS = {'.git', 'target', '.idea', '.settings', 'bin'}
    NAMESPACE = {'m': 'http://maven.apache.org/POM/4.0.0'}

    def __init__(self, logger=None):
        super().__init__()
        self.logger = logger if logger else self.get_logger("MavenHelper")
        self.logger.setLevel(logging.DEBUG)

    def process_repo(self, repo_dir: str, repo: object) -> List[Dependency]:
        self.logger.info(f"Processing Maven repo: {repo['repo_id']}")
        try:
            repo_path = Path(repo_dir).resolve()
            if not repo_path.exists():
                raise FileNotFoundError(f"Directory not found: {repo_dir}")

            effective_pom = self._generate_effective_pom(repo_path)
            if effective_pom:
                return self._parse_pom_file(effective_pom, repo, is_effective=True)

            root_pom = repo_path / "pom.xml"
            if root_pom.exists():
                pom_files = self._collect_module_poms(root_pom)
            else:
                pom_files = list(repo_path.rglob("pom.xml"))
                self.logger.warning("No root pom.xml found; scanning all poms under directory.")

            seen_dirs = set()
            unique_poms = [p for p in pom_files if p.parent not in seen_dirs and not seen_dirs.add(p.parent)]

            deps = []
            for pom in unique_poms:
                deps.extend(self._parse_pom_file(pom, repo))
            return deps

        except Exception as e:
            self.logger.error(f"Maven analysis failed: {str(e)}", exc_info=True)
            return []

    def _generate_effective_pom(self, repo_path: Path) -> Path:
        try:
            output_file = repo_path / "effective-pom.xml"
            command_list = [
                "mvn", "-B", "-q", "help:effective-pom",
                f"-Doutput={output_file.name}"
            ]

            if Config.TRUSTSTORE_PATH:
                command_list.append(f"-Djavax.net.ssl.trustStore={Config.TRUSTSTORE_PATH}")
            if Config.TRUSTSTORE_PASSWORD:
                command_list.append(f"-Djavax.net.ssl.trustStorePassword={Config.TRUSTSTORE_PASSWORD}")

            result = subprocess.run(
                command_list,
                cwd=repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30
            )
            if result.returncode != 0 or not output_file.exists():
                self.logger.warning("Effective POM generation failed.")
                self.logger.debug(result.stderr.decode().strip())
                return None
            return output_file
        except Exception as e:
            self.logger.warning(f"Error generating effective POM: {str(e)}")
            return None

    def _collect_module_poms(self, root_pom: Path, seen: Set[Path] = None) -> List[Path]:
        seen = seen or set()
        pom_files = []

        if not root_pom.exists():
            return []

        root_dir = root_pom.parent.resolve()
        if root_dir in seen or any(part in self.EXCLUDE_DIRS for part in root_dir.parts):
            return []
        seen.add(root_dir)

        pom_files.append(root_pom)

        try:
            tree = ET.parse(root_pom)
            root = tree.getroot()
            modules = root.find("m:modules", self.NAMESPACE)
            if modules is not None:
                for module in modules.findall("m:module", self.NAMESPACE):
                    module_dir = root_dir / module.text.strip()
                    module_pom = module_dir / "pom.xml"
                    pom_files.extend(self._collect_module_poms(module_pom, seen))
        except Exception as e:
            self.logger.warning(f"Error parsing modules in {root_pom}: {str(e)}")

        return pom_files

    def _resolve_parent(self, pom_path: Path) -> Dict[str, str]:
        try:
            tree = ET.parse(pom_path)
            root = tree.getroot()
            parent = root.find("m:parent", self.NAMESPACE)
            if parent is None:
                return {}

            rel_path_elem = parent.find("m:relativePath", self.NAMESPACE)
            rel_path = rel_path_elem.text.strip() if rel_path_elem is not None else "../pom.xml"
            parent_pom_path = (pom_path.parent / rel_path).resolve()

            if not parent_pom_path.exists():
                self.logger.debug(f"Parent POM not found at {parent_pom_path}")
                return {}

            parent_tree = ET.parse(parent_pom_path)
            parent_root = parent_tree.getroot()
            parent_group = parent_root.find("m:groupId", self.NAMESPACE)
            parent_version = parent_root.find("m:version", self.NAMESPACE)

            return {
                "groupId": parent_group.text.strip() if parent_group is not None else "",
                "version": parent_version.text.strip() if parent_version is not None else ""
            }

        except Exception as e:
            self.logger.warning(f"Error resolving parent POM from {pom_path}: {str(e)}")
            return {}

    def _parse_dependency_management(self, root: ET.Element) -> Dict[str, str]:
        managed_versions = {}
        for dm_dep in root.findall(".//m:dependencyManagement/m:dependencies/m:dependency", self.NAMESPACE):
            group = dm_dep.find("m:groupId", self.NAMESPACE)
            artifact = dm_dep.find("m:artifactId", self.NAMESPACE)
            version = dm_dep.find("m:version", self.NAMESPACE)
            if group is not None and artifact is not None and version is not None:
                key = f"{group.text.strip()}:{artifact.text.strip()}"
                managed_versions[key] = version.text.strip()
        return managed_versions

    def _parse_pom_file(self, pom_path: Path, repo: object, is_effective=False) -> List[Dependency]:
        deps = []
        try:
            tree = ET.parse(pom_path)
            root = tree.getroot()

            inherited = {}
            managed_versions = {}

            if not is_effective:
                project_group = root.find("m:groupId", self.NAMESPACE)
                project_version = root.find("m:version", self.NAMESPACE)
                if project_group is None or project_version is None:
                    inherited = self._resolve_parent(pom_path)
                managed_versions = self._parse_dependency_management(root)

            for dep_elem in root.findall(".//m:dependency", self.NAMESPACE):
                scope = dep_elem.find("m:scope", self.NAMESPACE)
                optional = dep_elem.find("m:optional", self.NAMESPACE)
                if scope is not None and scope.text == "test":
                    continue
                if optional is not None and optional.text.lower() == "true":
                    continue

                group = dep_elem.find("m:groupId", self.NAMESPACE)
                artifact = dep_elem.find("m:artifactId", self.NAMESPACE)
                version = dep_elem.find("m:version", self.NAMESPACE)

                group_val = group.text.strip() if group is not None else inherited.get("groupId", "unspecified")
                artifact_val = artifact.text.strip() if artifact is not None else "unspecified"

                key = f"{group_val}:{artifact_val}"
                if version is not None:
                    version_val = version.text.strip()
                else:
                    version_val = managed_versions.get(key, "unspecified")

                deps.append(Dependency(
                    repo_id=repo['repo_id'],
                    name=key,
                    version=version_val,
                    package_type="maven"
                ))
        except Exception as e:
            self.logger.warning(f"Error parsing POM {pom_path}: {str(e)}")
        return deps


# --- EXACT MAIN METHOD YOU PROVIDED ---

if __name__ == "__main__":
    repo_dir = "/tmp/maven-modular"
    repo_slug = "maven-modular"
    repo_id = "maven-modular"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug
            self.repo_name = repo_slug
        def __getitem__(self, key):
            return getattr(self, key)

    repo = MockRepo(repo_id, repo_slug)
    helper = MavenHelper()
    helper.logger.setLevel(logging.INFO)

    try:
        deps = helper.process_repo(repo_dir, repo)
        print(f"Found {len(deps)} Maven dependencies:")
        for dep in deps[:10]:
            print(f"{dep.name}@{dep.version}")
    except Exception as e:
        helper.logger.error(f"Error processing repo {repo_id}: {str(e)}", exc_info=True)