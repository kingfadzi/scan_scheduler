#!/usr/bin/env python3
from pathlib import Path
import re
import yaml
import argparse
import sys
import logging
from typing import Optional, List, Dict, Tuple
from modular.shared.models import Session
from modular.shared.execution_decorator import analyze_execution

class GradleJDKAnalyzer:
    SCRIPT_DIR = Path(__file__).parent.resolve()
    GRADLE_RULES_FILE = SCRIPT_DIR / 'gradle_rules.yaml'
    JDK_MAPPING_FILE = SCRIPT_DIR / 'jdk_mapping.yaml'
    EXCLUDE_DIRS = {'.gradle', 'build', 'out', 'target', '.git', '.idea'}

    def __init__(self, logger=None):
        if logger is None:
            self.logger = logging.getLogger("GradleJDKAnalyzer")
            if not self.logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('%(levelname)s - %(message)s')
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
        else:
            self.logger = logger
        self.logger.setLevel(logging.DEBUG)
        self.rules: List[Dict] = []
        self.jdk_mapping: Dict = {}

    def load_config(self) -> None:
        """Load and validate configuration files"""
        config_errors = []
        if not self.GRADLE_RULES_FILE.exists():
            config_errors.append(f"Missing rules file at {self.GRADLE_RULES_FILE}")
        if not self.JDK_MAPPING_FILE.exists():
            config_errors.append(f"Missing JDK mapping at {self.JDK_MAPPING_FILE}")
        if config_errors:
            raise FileNotFoundError("\n".join(config_errors))
        
        try:
            with open(self.GRADLE_RULES_FILE, 'r') as f:
                self.rules = yaml.safe_load(f)['extraction_rules']
            with open(self.JDK_MAPPING_FILE, 'r') as f:
                self.jdk_mapping = yaml.safe_load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to load configuration: {str(e)}")

    def find_gradle_files(self, root: Path) -> List[Path]:
        """Find Gradle configuration files, excluding specified directories"""
        gradle_files = []
        
        for path in root.rglob('*'):
            if any(part in self.EXCLUDE_DIRS for part in path.parts):
                self.logger.debug(f"Skipping excluded path: {path}")
                continue
                
            if not path.is_file():
                continue

            if path.parts[-3:] == ('gradle', 'wrapper', 'gradle-wrapper.properties'):
                gradle_files.append(path)
                self.logger.debug(f"Found wrapper properties: {path}")
                continue

            if path.name in {'build.gradle', 'build.gradle.kts',
                            'settings.gradle', 'settings.gradle.kts',
                            'gradle.properties'}:
                gradle_files.append(path)
                self.logger.debug(f"Found Gradle file: {path}")

        return sorted(gradle_files, key=lambda p: 0 if 'wrapper' in p.parts else 1)

    def extract_version(self, content: str, pattern: str) -> Optional[str]:
        """Extract version using regex pattern"""
        try:
            self.logger.debug(f"Applying regex: {pattern}")
            if match := re.search(pattern, content, re.MULTILINE):
                version = match.group(1).split('-')[0]
                self.logger.debug(f"Matched version: {version}")
                return version
        except Exception as e:
            self.logger.error(f"Regex error: {str(e)}")
        return None

    def find_jdk_version(self, gradle_version: str) -> str:
        """Find compatible JDK version using hierarchical lookup"""
        parts = gradle_version.split('.')
        while parts:
            lookup = '.'.join(parts)
            if jdk := self.jdk_mapping.get(lookup):
                return jdk
            parts.pop()
        return "JDK version unknown"

    @analyze_execution(session_factory=Session, stage="Gradle jdk Analysis")
    def run_analysis(self, repo_dir, repo, session, run_id=None):
        """Decorated analysis workflow with execution tracking"""
        # Validate repository path
        repo_path = Path(repo_dir).resolve()
        if not repo_path.exists():
            raise ValueError(f"Path does not exist - {repo_path}")
        if not repo_path.is_dir():
            raise ValueError(f"Path is not a directory - {repo_path}")

        # Load configuration
        self.load_config()

        # Find and process files
        found_files = self.find_gradle_files(repo_path)
        self.logger.debug(f"Found {len(found_files)} potential Gradle files")
        if not found_files:
            raise RuntimeError("No Gradle configuration files found")

        gradle_version = None
        for file in found_files:
            try:
                content = file.read_text(encoding='utf-8')
                self.logger.debug(f"Checking file: {file.relative_to(repo_path)}")
                sample_content = content[:200].replace('\n', ' ')
                self.logger.debug(f"Content sample: {sample_content}...")
                for rule in self.rules:
                    try:
                        if file.match(rule['file']):
                            self.logger.debug(f"Applying rule: {rule['regex']}")
                            if version := self.extract_version(content, rule['regex']):
                                self.logger.info(f"Found Gradle {version} in {file.relative_to(repo_path)}")
                                gradle_version = version
                                break
                    except Exception as e:
                        self.logger.error(f"Rule processing error: {str(e)}")
                        continue
                
                if gradle_version:
                    break
            except Exception as e:
                self.logger.error(f"File processing error: {str(e)}")

        if not gradle_version:
            error_msg = [
                "No Gradle version detected. Possible reasons:",
                "- Version not declared in standard locations",
                "- Version format doesn't match regex patterns",
                "- Missing gradle-wrapper.properties file",
                "\nChecked files:"
            ] + [f"  - {f.relative_to(repo_path)}" for f in found_files]
            raise RuntimeError("\n".join(error_msg))
        
        jdk_version = self.find_jdk_version(gradle_version)
        return gradle_version, jdk_version

def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Detect Gradle version and required JDK for a project',
        epilog='Configuration files must be in same directory as script'
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Path to repository root (default: current directory)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable debug output'
    )
    return parser.parse_args()

def main():
    args = parse_args()
    
    analyzer = GradleJDKAnalyzer()
    if not args.verbose:
        analyzer.logger.setLevel(logging.INFO)
    
    try:
        repo_root = Path(args.path).resolve()
        gradle_version, jdk_version = analyzer.run_analysis(
            repo_dir=repo_root,
            repo=None,  # Should be replaced with actual repo object if needed
            session=Session(),
            run_id=None
        )
    except Exception as e:
        analyzer.logger.error(e)
        sys.exit(1)
    
    print(f"\nAnalysis results for {repo_root}:")
    print(f"• Detected Gradle version: {gradle_version}")
    print(f"• Required JDK version:   {jdk_version}")

if __name__ == "__main__":
    main()