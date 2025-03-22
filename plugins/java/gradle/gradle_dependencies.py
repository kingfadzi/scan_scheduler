from pathlib import Path
import re
import logging
from typing import List, Dict
from shared.base_logger import BaseLogger
from shared.models import Dependency

class GradleDependencyAnalyzer(BaseLogger):
    EXCLUDE_DIRS = {'.gradle', 'build', 'out', 'target', '.git', '.idea', '.settings', 'bin'}
    DEPENDENCY_PATTERNS = [
        r"(?:implementation|api|compile|runtimeOnly|testImplementation)\s+['\"](.*?:.*?:.*?)['\"]",
        r"(?:implementation|api|compile|runtimeOnly|testImplementation)\s*group:\s*['\"](.*?)['\"],\s*name:\s*['\"](.*?)['\"],\s*version:\s*['\"](.*?)['\"]",
        r"(?:implementation|api|compile|runtimeOnly|testImplementation)[\s\n]*\"(.*?)\""
    ]

    def __init__(self, logger=None):
        super().__init__()
        self.logger = logger if logger else self.get_logger("GradleHelper")
        self.logger.setLevel(logging.DEBUG)

    def process_repo(self, repo_dir: str, repo: object) -> List[Dependency]:
        self.logger.info(f"Processing Gradle repo: {repo['repo_id']}")
        try:
            repo_path = Path(repo_dir).resolve()
            if not repo_path.exists():
                raise FileNotFoundError(f"Directory not found: {repo_dir}")

            build_files = self._find_gradle_files(repo_path)
            raw_deps = self._analyze_build_files(build_files)
            return self._format_dependencies(raw_deps, repo)

        except Exception as e:
            self.logger.error(f"Gradle analysis failed: {str(e)}", exc_info=True)
            return []

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

    def _format_dependencies(self, raw_deps: List[Dict], repo: object) -> List[Dependency]:
        return [
            Dependency(
                repo_id=repo['repo_id'],
                name=f"{dep['group']}:{dep['artifact']}",
                version=dep.get('version', 'unknown'),
                package_type="gradle"
            )
            for dep in raw_deps
        ]

if __name__ == "__main__":
    class MockRepo:
        def __init__(self, repo_id):
            self.repo_id = repo_id

    helper = GradleDependencyAnalyzer()
    helper.logger.setLevel(logging.INFO)

    repo = MockRepo("test-org/example")
    dependencies = helper.process_repo("/tmp/gradle-example", repo)

    print(f"Found {len(dependencies)} Gradle dependencies:")
    for dep in dependencies[:3]:
        print(f"{dep.name}@{dep.version}")
