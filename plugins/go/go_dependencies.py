import os
import re
import logging

from shared.models import Dependency, Session
from shared.base_logger import BaseLogger
from shared.execution_decorator import analyze_execution
from shared.utils import Utils

class GoDependencyAnalyzer(BaseLogger):
    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)
        self.utils = Utils(logger=self.logger)  # Centralized initialization
        self.dep_regex = re.compile(
            r'^\s*require\s+(?:\(\s*)?([\w\.\/-]+)\s+([\w\.\/-]+)',
            re.MULTILINE
        )

    @analyze_execution(
        session_factory=Session,
        stage="Go Dependency Analysis",
        require_language="go"
    )
    def run_analysis(self, repo_dir, repo):
        self.logger.info(f"Processing repository at: {repo_dir}")
        all_deps = []

        for root, _, files in os.walk(repo_dir):
            if "go.mod" in files:
                module_dir = root
                self.logger.info(f"Analyzing module in: {module_dir}")
                deps = self.parse_go_mod(module_dir, repo)
                all_deps.extend(deps)

        self.utils.persist_dependencies(all_deps)  # Use instance utility
        return f"{len(all_deps)} dependencies found."

    def parse_go_mod(self, module_dir, repo):
        """Parse go.mod using regex patterns"""
        deps = []
        go_mod_path = os.path.join(module_dir, "go.mod")
        
        if not os.path.exists(go_mod_path):
            return deps

        try:
            with open(go_mod_path, 'r') as f:
                content = f.read()
                matches = self.dep_regex.findall(content)
                
                for module, version in matches:
                    clean_version = version.split('//')[0].strip()
                    deps.append(Dependency(
                        repo_id=repo['repo_id'],
                        name=module,
                        version=clean_version,
                        package_type="go"
                    ))
                
        except Exception as e:
            self.logger.error(f"Failed to parse {go_mod_path}: {str(e)}")
        
        return deps
        
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    analyzer = GoDependencyAnalyzer()
    repo_path = "/Users/fadzi/tools/go_projetcs/ovaa"
    repo_data = {"repo_id": "go_project"}

    try:
        result = analyzer.run_analysis(repo_path, repo_data)
        print(result)
    except Exception as e:
        print(f"Analysis failed: {e}")
