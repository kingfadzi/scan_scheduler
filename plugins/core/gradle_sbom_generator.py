import os
import re
import json
import logging
from pathlib import Path
from typing import List, Dict
from shared.base_logger import BaseLogger


class GradleSbomGenerator(BaseLogger):
    EXCLUDE_DIRS = {'.gradle', 'build', 'out', 'target', '.git', '.idea', '.settings', 'bin'}
    DEPENDENCY_PATTERNS = [
        r"(?:implementation|api|compile|runtimeOnly|testImplementation|compileOnly|annotationProcessor)\s*?\s*['\"]([^'\"]+:[^'\"]+:[^'\"]+)['\"]\s*?",
        r"(?:implementation|api|compile|runtimeOnly|testImplementation|compileOnly|annotationProcessor)\s*?\s*group\s*:\s*['\"](.*?)['\"],\s*name\s*:\s*['\"](.*?)['\"],\s*version\s*:\s*['\"](.*?)['\"]\s*?"
    ]

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)

    def run_analysis(self, repo_dir: str, repo: dict) -> str:
        self.logger.info(f"Starting Gradle SBOM generation for {repo['repo_id']}")

        repo_dir = os.path.abspath(repo_dir)
        if not os.path.exists(repo_dir):
            raise FileNotFoundError(f"Directory not found: {repo_dir}")

        repo_path = Path(repo_dir)

        build_files = self._find_gradle_files(repo_path)

        if not build_files:
            self.logger.warning(f"No Gradle build files found for {repo['repo_id']}, skipping SBOM generation.")
            return "No Gradle build files found, no SBOM generated."

        raw_deps = self._analyze_build_files(build_files)
        if not raw_deps:
            self.logger.warning(f"No dependencies found in Gradle build files for {repo['repo_id']}.")

        sbom_path = self._generate_sbom(repo_dir, repo, raw_deps)

        msg = f"Gradle SBOM generated at {sbom_path} with {len(raw_deps)} dependencies."
        self.logger.info(msg)
        return msg

    def _find_gradle_files(self, root: Path) -> List[Path]:
        build_files = []
        settings_files = list(root.glob("settings.gradle*"))
        module_paths = self._parse_settings_files(settings_files, root)

        search_paths = [root] + module_paths
        for path in search_paths:
            for build_file in path.glob("build.gradle*"):
                if not any(part in self.EXCLUDE_DIRS for part in build_file.parts):
                    build_files.append(build_file)
        return build_files

    def _parse_settings_files(self, settings_files: List[Path], root: Path) -> List[Path]:
        module_paths = []
        for sf in settings_files:
            try:
                content = sf.read_text(encoding='utf-8')
                includes = re.findall(r"include\s*['\"](.*?)['\"]", content, re.IGNORECASE)
                includes += re.findall(r"include\s+['\"](.*?)['\"]", content)

                for module_path in includes:
                    fs_path = module_path.replace(':', '/').replace('.', '/')
                    full_path = root / fs_path
                    if full_path.exists():
                        module_paths.append(full_path)
            except Exception as e:
                self.logger.warning(f"Error parsing {sf.name}: {str(e)}")
        return module_paths

    def _analyze_build_files(self, build_files: List[Path]) -> List[Dict]:
        dependencies = []
        for bf in build_files:
            try:
                content = bf.read_text(encoding='utf-8')
                dependencies.extend(self._extract_dependencies(content))
            except Exception as e:
                self.logger.warning(f"Error processing {bf.name}: {str(e)}")
        return dependencies

    def _extract_dependencies(self, content: str) -> List[Dict]:
        dependencies = []
        for block_match in re.finditer(r"(allprojects|subprojects)\s*\{([^}]*)\}", content, re.DOTALL):
            block_content = block_match.group(2)
            dependencies.extend(self._parse_dependency_block(block_content))
        dependencies.extend(self._parse_dependency_block(content))
        return dependencies

    def _parse_dependency_block(self, content: str) -> List[Dict]:
        deps = []
        for pattern in self.DEPENDENCY_PATTERNS:
            for match in re.finditer(pattern, content):
                try:
                    if match.lastindex == 1:
                        dep = self._parse_string_style(match)
                    else:
                        dep = self._parse_map_style(match)
                    deps.append(dep)
                except Exception as e:
                    self.logger.warning(f"Skipping invalid dependency: {str(e)}")
        return deps

    def _parse_map_style(self, match) -> Dict:
        return {
            'group': match.group(1).strip(),
            'artifact': match.group(2).strip(),
            'version': match.group(3).strip()
        }

    def _parse_string_style(self, match) -> Dict:
        parts = match.group(1).split(':')
        if len(parts) < 3:
            raise ValueError(f"Invalid dependency: {match.group(1)}")
        return {
            'group': parts[0].strip(),
            'artifact': parts[1].strip(),
            'version': parts[2].strip()
        }

    def _generate_sbom(self, repo_dir: str, repo: dict, dependencies: List[Dict]) -> str:
        sbom_path = os.path.join(repo_dir, "sbom.json")

        artifacts = []
        for dep in dependencies:
            try:
                purl = f"pkg:maven/{dep['group']}/{dep['artifact']}@{dep['version']}"
                artifact_entry = {
                    "name": dep['artifact'],
                    "version": dep['version'],
                    "type": "library",
                    "purl": purl
                }
                artifacts.append(artifact_entry)
            except Exception as e:
                self.logger.warning(f"Skipping invalid dependency entry: {dep}: {str(e)}")

        sbom_data = {
            "artifacts": artifacts,
            "source": {
                "type": "gradle-project",
                "name": repo["repo_name"]
            },
            "distro": {},
            "descriptor": {
                "name": "generated-gradle-sbom",
                "version": "0.0.1"
            },
            "schema": "https://raw.githubusercontent.com/anchore/syft/main/schema/json/schema-1.0.1.json"
        }

        with open(sbom_path, "w") as f:
            json.dump(sbom_data, f, indent=2)

        return sbom_path
        
import sys
import os

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python gradle_sbom_generator.py /path/to/repo_dir")
        sys.exit(1)

    repo_dir = sys.argv[1]
    repo_name = os.path.basename(os.path.normpath(repo_dir))
    repo_slug = repo_name
    repo_id = f"standalone_test/{repo_slug}"

    repo = {
        "repo_id": repo_id,
        "repo_slug": repo_slug,
        "repo_name": repo_name
    }

    analyzer = GradleSbomGenerator(run_id="STANDALONE_RUN_ID_001")

    try:
        analyzer.logger.info(f"Starting standalone Gradle SBOM generation for repo_id: {repo['repo_id']}")
        result = analyzer.run_analysis(repo_dir, repo=repo)
        analyzer.logger.info(f"Standalone Gradle SBOM generation result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone Gradle SBOM generation: {e}")