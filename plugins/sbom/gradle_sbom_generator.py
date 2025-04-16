import os
import re
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict
from shared.base_logger import BaseLogger

class GradleSbomGenerator(BaseLogger):
    EXCLUDE_DIRS = {'.gradle', 'build', 'out', 'target', '.git', '.idea', '.settings', 'bin'}
    DEPENDENCY_PATTERNS = [
        r"""(?x)
        (?:implementation|api|compile|runtimeOnly|
        testImplementation|compileOnly|annotationProcessor)
        \s*\(?\s*['"](?P<coord>[^'":]+:[^'":]+(:[^'"]+)?)['"]\s*\)?
        """,
        r"""(?x)
        (?:implementation|api|compile|runtimeOnly|
        testImplementation|compileOnly|annotationProcessor)
        \s+\{\s*
            group\s*:\s*['"](?P<group>[^'"]+)['"]\s*,\s*
            name\s*:\s*['"](?P<name>[^'"]+)['"]\s*
            (?:,\s*version\s*:\s*['"](?P<version>[^'"]+)['"])?\s*
        \}
        """
    ]

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)
        self.logger.debug("Initialized GradleSbomGenerator instance")

    def run_analysis(self, repo_dir: str, repo: dict) -> str:
        self.logger.info(f"[{repo['repo_id']}] Starting Gradle SBOM generation")
        self.logger.debug(f"Resolved absolute path: {os.path.abspath(repo_dir)}")

        repo_path = Path(repo_dir)
        if not repo_path.exists():
            self.logger.error(f"Directory not found: {repo_path}")
            raise FileNotFoundError(f"Directory not found: {repo_path}")

        self.logger.debug(f"Searching for Gradle files in: {repo_path}")
        build_files = self._find_gradle_files(repo_path)
        
        self.logger.info(f"Found {len(build_files)} build files for analysis")
        if not build_files:
            self.logger.warning("No Gradle build files found, skipping SBOM generation")
            return "No Gradle build files found, no SBOM generated."

        self.logger.debug("Starting dependency extraction from build files")
        raw_deps = self._analyze_build_files(build_files)
        
        self.logger.info(f"Extracted {len(raw_deps)} raw dependencies")
        if not raw_deps:
            self.logger.warning("No dependencies found in build files")

        self.logger.debug("Generating SBOM JSON structure")
        sbom_path = self._generate_sbom(repo_dir, repo, raw_deps)
        
        self.logger.info(f"SBOM generation completed successfully at: {sbom_path}")
        return f"Gradle SBOM generated at {sbom_path} with {len(raw_deps)} dependencies."

    def _find_gradle_files(self, root: Path) -> List[Path]:
        self.logger.debug(f"Scanning for Gradle files in: {root}")
        build_files = []
        
        settings_files = list(root.glob("settings.gradle*"))
        self.logger.info(f"Found {len(settings_files)} settings files")
        
        module_paths = self._parse_settings_files(settings_files, root)
        search_paths = [root] + module_paths
        
        self.logger.debug(f"Searching in {len(search_paths)} locations for build files")
        for path in search_paths:
            self.logger.debug(f"Scanning directory: {path}")
            for build_file in path.glob("build.gradle*"):
                if any(part in self.EXCLUDE_DIRS for part in build_file.parts):
                    self.logger.debug(f"Skipping excluded file: {build_file}")
                    continue
                self.logger.info(f"Found build file: {build_file}")
                build_files.append(build_file)
        
        self.logger.debug(f"Total build files found: {len(build_files)}")
        return build_files

    def _parse_settings_files(self, settings_files: List[Path], root: Path) -> List[Path]:
        module_paths = []
        self.logger.info(f"Parsing {len(settings_files)} settings files")
        
        for sf in settings_files:
            self.logger.debug(f"Processing settings file: {sf}")
            try:
                content = sf.read_text(encoding='utf-8')
                includes = re.findall(r"include\s*['\"](.*?)['\"]", content, re.IGNORECASE)
                includes += re.findall(r"include\s+['\"](.*?)['\"]", content)
                self.logger.debug(f"Found {len(includes)} includes in {sf.name}")

                for module_path in includes:
                    fs_path = module_path.replace(':', '/').replace('.', '/')
                    full_path = root / fs_path
                    if full_path.exists():
                        self.logger.debug(f"Adding module path: {full_path}")
                        module_paths.append(full_path)
                    else:
                        self.logger.warning(f"Module path does not exist: {full_path}")
            except Exception as e:
                self.logger.error(f"Failed to parse {sf}: {str(e)}", exc_info=True)
        
        self.logger.info(f"Resolved {len(module_paths)} module paths from settings files")
        return module_paths

    def _analyze_build_files(self, build_files: List[Path]) -> List[Dict]:
        dependencies = []
        self.logger.info(f"Analyzing {len(build_files)} build files")
        
        for bf in build_files:
            self.logger.debug(f"Processing build file: {bf}")
            try:
                content = bf.read_text(encoding='utf-8')
                deps = self._extract_dependencies(content)
                self.logger.debug(f"Found {len(deps)} dependencies in {bf.name}")
                dependencies.extend(deps)
            except Exception as e:
                self.logger.error(f"Failed to process {bf}: {str(e)}", exc_info=True)
        
        self.logger.debug(f"Total dependencies collected: {len(dependencies)}")
        return dependencies

    def _extract_dependencies(self, content: str) -> List[Dict]:
        dependencies = []
        self.logger.debug("Searching for dependency blocks")
        
        for block_match in re.finditer(r"(allprojects|subprojects)\s*\{([^}]*)\}", content, re.DOTALL):
            block_type = block_match.group(1)
            self.logger.debug(f"Found {block_type} block")
            block_content = block_match.group(2)
            deps = self._parse_dependency_block(block_content)
            self.logger.info(f"Found {len(deps)} dependencies in {block_type} block")
            dependencies.extend(deps)
        
        main_deps = self._parse_dependency_block(content)
        self.logger.info(f"Found {len(main_deps)} dependencies in main build file")
        dependencies.extend(main_deps)
        
        return dependencies

    def _parse_dependency_block(self, content: str) -> List[Dict]:
        deps = []
        self.logger.debug("Parsing dependency block")
        
        for idx, pattern in enumerate(self.DEPENDENCY_PATTERNS, 1):
            self.logger.debug(f"Using pattern {idx}: {pattern[:50]}...")
            matches = list(re.finditer(pattern, content))
            self.logger.info(f"Found {len(matches)} matches for pattern {idx}")
            
            for match in matches:
                self.logger.debug(f"Processing match: {match.group()[:50]}...")
                try:
                    if match.lastindex == 1:
                        dep = self._parse_string_style(match)
                    else:
                        dep = self._parse_map_style(match)
                    self.logger.debug(f"Parsed dependency: {dep}")
                    deps.append(dep)
                except Exception as e:
                    self.logger.warning(f"Skipping invalid dependency: {str(e)}")
                    self.logger.debug(f"Problematic match: {match.group()}")
        
        self.logger.debug(f"Returning {len(deps)} dependencies from block")
        return deps

    
    def _parse_string_style(self, match) -> Dict:
        coord = match.group("coord")
        self.logger.debug(f"Parsing string-style dependency: {coord}")
        
        parts = coord.split(':')
        self.logger.debug(f"Split into {len(parts)} parts: {parts}")
    
        version = "unknown"
        group = "unknown"
        artifact = "unknown"
    
        if len(parts) >= 3:
            version = parts[-1].strip() or "unknown"
            artifact = parts[-2].strip()
            group = ':'.join(part.strip() for part in parts[:-2])
        elif len(parts) == 2:
            group = parts[0].strip()
            artifact = parts[1].strip()
        else:
            error_msg = f"Invalid dependency format: {coord}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)
    
        if version == "unknown":
            self.logger.warning(f"No version specified for dependency: {group}:{artifact}, defaulting to 'unknown'.")
    
        self.logger.info(f"Parsed string-style: {group}:{artifact}@{version}")
        return {
            'group': group,
            'artifact': artifact,
            'version': version
        }
        return {
            'group': group,
            'artifact': artifact,
            'version': version
        }
    
    def _parse_map_style(self, match) -> Dict:
        self.logger.debug("Parsing map-style dependency")
        
        group = match.group("group").strip()
        artifact = match.group("name").strip()
        version = match.group("version").strip() if match.group("version") else "unknown"
    
        if version == "unknown":
            self.logger.warning(f"No version specified for dependency: {group}:{artifact}, defaulting to 'unknown'.")
    
        self.logger.info(f"Parsed map-style: {group}:{artifact}@{version}")
        return {
            'group': group,
            'artifact': artifact,
            'version': version
        }
    
    
    def _generate_sbom(self, repo_dir: str, repo: dict, dependencies: List[Dict]) -> str:
        self.logger.info("Generating SBOM JSON structure")
        sbom_path = os.path.join(repo_dir, "sbom.json")
        self.logger.debug(f"Target SBOM path: {sbom_path}")
        
        sbom_data = {
            "artifacts": [],
            "source": {
                "type": "directory",
                "target": {
                    "path": repo_dir,
                    "type": "application",
                    "name": repo["repo_name"]
                }
            },
            "distro": {},
            "descriptor": {
                "name": "gradle-sbom-generator",
                "version": "0.1.0",
                "configuration": {
                    "excludePatterns": list(self.EXCLUDE_DIRS)
                }
            },
            "schema": {
                "version": "16.0.24",
                "url": "https://raw.githubusercontent.com/anchore/syft/main/schema/json/schema-16.0.24.json"
            }
        }

        self.logger.info(f"Processing {len(dependencies)} dependencies for SBOM")
        for idx, dep in enumerate(dependencies, 1):
            self.logger.debug(f"Processing dependency {idx}/{len(dependencies)}")
            try:
                artifact_entry = {
                    "type": "java-archive",
                    "name": dep['artifact'],
                    "version": dep['version'] if dep['version'] != "unknown" else None,
                    "language": "java",
                    "locations": [{
                        "path": f"pkg:gradle/{dep['group']}/{dep['artifact']}",
                        "annotations": {
                            "scope": "dependencies"
                        }
                    }],
                    "purl": f"pkg:maven/{dep['group']}/{dep['artifact']}" +
                            (f"@{dep['version']}" if dep['version'] != "unknown" else ""),
                    "metadata": {
                        "gradle": {
                            "configuration": dep.get('configuration', 'implementation'),
                            "group": dep['group']
                        },
                        "pomProperties": {
                            "groupId": dep['group'],
                            "artifactId": dep['artifact'],
                            "version": dep['version'] if dep['version'] != "unknown" else ""
                        }
                    },
                    "licenses": []
                }

                sbom_data["artifacts"].append(artifact_entry)
                self.logger.debug(f"Added artifact: {artifact_entry['purl']}")
            except Exception as e:
                self.logger.error(f"Failed to process dependency: {str(e)}")
                self.logger.debug(f"Invalid dependency data: {dep}")

        self.logger.debug("Writing SBOM to disk")
        with open(sbom_path, "w") as f:
            json.dump(sbom_data, f, indent=2, default=lambda o: None)
        
        self.logger.info(f"SBOM file created ({os.path.getsize(sbom_path)} bytes)")
        return sbom_path

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
        analyzer.logger.debug(f"Received command line arguments: {sys.argv}")
        analyzer.logger.info("Starting standalone execution")
        result = analyzer.run_analysis(repo_dir, repo=repo)
        analyzer.logger.info("Standalone execution completed successfully")
        analyzer.logger.info(f"Standalone Gradle SBOM generation result: {result}")
    except Exception as e:
        analyzer.logger.critical("Fatal error in standalone execution", exc_info=True)
        sys.exit(1)
