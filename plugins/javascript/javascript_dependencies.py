import os
import sys
import json
import logging
import subprocess

from shared.language_required_decorator import language_required
from shared.models import Dependency, Session
from shared.base_logger import BaseLogger
from shared.execution_decorator import analyze_execution
from shared.utils import Utils


class JavaScriptDependencyAnalyzer(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)

    @analyze_execution(
        session_factory=Session,
        stage="Javascript Dependency Analysis",
        require_language=["JavaScript", "TypeScript"]
    )
    def run_analysis(self, repo_dir, repo, generate_lock_files=False):
        try:
            utils = Utils()
            dependencies = []

            for root, _, files in os.walk(repo_dir):
                if "package.json" in files:
                    pkg_dir = root
                    self.logger.debug(f"Found package.json at: {os.path.join(pkg_dir, 'package.json')}")
                    
                    # Process lock files for this package
                    lock_files = self.process_directory(pkg_dir, generate_lock_files)
                    
                    for lock_file in lock_files:
                        deps = self.parse_dependencies(lock_file, repo)
                        dependencies.extend(deps)

            utils.persist_dependencies(dependencies)
            return f"{len(dependencies)} dependencies found."
        except Exception as e:
            self.logger.error(f"Analysis failed: {e}", exc_info=True)
            raise

    def process_directory(self, pkg_dir, generate_lock_files):
        """Handle lock file processing for a single package directory"""
        lock_files = self.find_lock_files(pkg_dir)
        
        if not lock_files and generate_lock_files:
            self.logger.info(f"Attempting lock file generation in {pkg_dir}")
            generated = self.generate_lock_files(pkg_dir)
            if generated:
                lock_files = self.find_lock_files(pkg_dir)
        
        if not lock_files:
            self.logger.warning(f"No lock files found in {pkg_dir}")
            return []
            
        return lock_files

    def find_lock_files(self, directory):
        """Identify existing lock files in directory"""
        lock_files = []
        for name in ["package-lock.json", "yarn.lock"]:
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                lock_files.append(path)
                self.logger.info(f"Found lock file: {path}")
        return lock_files

    def generate_lock_files(self, pkg_dir):
        """Generate lock files through package manager install"""
        try:
            pkg_json = os.path.join(pkg_dir, "package.json")
            pm = self.detect_package_manager(pkg_json)
            success = self.install_dependencies(pkg_dir, pm)
            return success
        except Exception as e:
            self.logger.error(f"Generation failed in {pkg_dir}: {e}")
            return False

    def detect_package_manager(self, pkg_json_path):
        """Determine package manager from package.json"""
        try:
            with open(pkg_json_path, "r") as f:
                pkg_data = json.load(f)
            if "packageManager" in pkg_data and "yarn" in pkg_data["packageManager"]:
                return "yarn"
        except Exception as e:
            self.logger.error(f"Error reading package.json: {e}")
        return "npm"

    def install_dependencies(self, dir_path, pm):
        """Run package manager install command"""
        cmd = ["yarn", "install"] if pm == "yarn" else ["npm", "install"]
        self.logger.info(f"Running {' '.join(cmd)} in {dir_path}")
        
        try:
            result = subprocess.run(
                cmd,
                cwd=dir_path,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            self.logger.debug(f"Install output:\n{result.stdout}")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Install failed in {dir_path}")
            self.logger.error(f"Error output:\n{e.stderr}")
            return False

    def parse_dependencies(self, lock_file, repo):
        """Extract dependencies from lock file"""
        dependencies = []
        
        try:
            if lock_file.endswith("package-lock.json"):
                with open(lock_file, "r", encoding="utf-8") as f:
                    lock_data = json.load(f)
                
                if "dependencies" in lock_data:
                    for name, details in lock_data["dependencies"].items():
                        dependencies.append(Dependency(
                            repo_id=repo['repo_id'],
                            name=name,
                            version=details.get("version", "unknown"),
                            package_type="npm"
                        ))

            elif lock_file.endswith("yarn.lock"):
                with open(lock_file, "r", encoding="utf-8") as f:
                    current_name = None
                    current_version = None
                    
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                            
                        if line.startswith("version"):
                            current_version = line.split(" ")[-1].strip('"')
                        elif '"' in line and "@" in line and not line.startswith("  "):
                            current_name = line.split("@")[0].strip('"')
                            
                        if current_name and current_version:
                            dependencies.append(Dependency(
                                repo_id=repo['repo_id'],
                                name=current_name,
                                version=current_version,
                                package_type="yarn"
                            ))
                            current_name = None
                            current_version = None

        except Exception as e:
            self.logger.error(f"Failed to parse {lock_file}: {str(e)}")
            
        return dependencies


class Repo:
    """Simple repository representation"""
    def __init__(self, repo_id):
        self.repo_id = repo_id

    def __getitem__(self, key):
        return getattr(self, key) if key == 'repo_id' else None


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if len(sys.argv) < 2:
        print("Usage: python javascript_analyzer.py /path/to/repo")
        sys.exit(1)

    repo_directory = os.path.abspath(sys.argv[1])
    
    # Convert Repo instance to dictionary format
    repo_instance = Repo(repo_id=os.path.basename(repo_directory))
    repo_dict = {
        'repo_id': repo_instance.repo_id,
        # Add other required fields if needed
    }
    
    analyzer = JavaScriptDependencyAnalyzer(
        run_id="STANDALONE_RUN_001"
    )

    GENERATE_LOCK_FILES = False

    try:
        result = analyzer.run_analysis(
            repo_directory,
            repo_dict,  # Pass the dictionary instead of Repo instance
            generate_lock_files=GENERATE_LOCK_FILES
        )
        print(f"Analysis complete. {result}")
    except Exception as e:
        print(f"Analysis failed: {str(e)}")
        sys.exit(1)