#!/usr/bin/env python3
from pathlib import Path
import re
import yaml
import argparse
import sys
from typing import Optional


# Configuration
SCRIPT_DIR = Path(__file__).parent.resolve()
GRADLE_RULES_FILE = SCRIPT_DIR / 'gradle_rules.yaml'
JDK_MAPPING_FILE = SCRIPT_DIR / 'jdk_mapping.yaml'
EXCLUDE_DIRS = {'.gradle', 'build', 'out', 'target', '.git', '.idea'}

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
    return parser.parse_args()

def find_gradle_files(root: Path) -> list[Path]:
    """Locate Gradle configuration files with exclusions"""
    gradle_files = []
    
    for path in root.rglob('*'):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
            
        if path.name in {'build.gradle', 'build.gradle.kts', 
                        'settings.gradle', 'settings.gradle.kts',
                        'gradle.properties'}:
            gradle_files.append(path)
        elif path.parts[-2:] == ('gradle', 'wrapper') and path.name == 'gradle-wrapper.properties':
            gradle_files.append(path)
    
    return gradle_files

def extract_version(content: str, pattern: str) -> Optional[str]:
    """Extract and normalize Gradle version"""
    if match := re.search(pattern, content):
        return match.group(1).split('-')[0]
    return None

def find_jdk_version(gradle_version: str, mapping: dict) -> str:
    """Hierarchical JDK version lookup"""
    parts = gradle_version.split('.')
    while parts:
        lookup = '.'.join(parts)
        if jdk := mapping.get(lookup):
            return jdk
        parts.pop()
    return "JDK version unknown"

def main():
    args = parse_args()
    
    # Validate configuration files
    if not GRADLE_RULES_FILE.exists():
        print(f"Error: Missing rules file at {GRADLE_RULES_FILE}")
        sys.exit(1)
    if not JDK_MAPPING_FILE.exists():
        print(f"Error: Missing JDK mapping at {JDK_MAPPING_FILE}")
        sys.exit(1)

    # Load configuration
    try:
        with open(GRADLE_RULES_FILE) as f:
            rules = yaml.safe_load(f)['extraction_rules']
        with open(JDK_MAPPING_FILE) as f:
            jdk_mapping = yaml.safe_load(f)
    except Exception as e:
        print(f"Configuration error: {str(e)}")
        sys.exit(1)

    # Validate repository path
    repo_root = Path(args.path).resolve()
    if not repo_root.exists():
        print(f"Error: Path does not exist - {repo_root}")
        sys.exit(1)
    if not repo_root.is_dir():
        print(f"Error: Path is not a directory - {repo_root}")
        sys.exit(1)

    # Process files
    found_files = find_gradle_files(repo_root)
    gradle_version = None
    
    for file in sorted(found_files, key=lambda p: p.as_posix()):
        try:
            content = file.read_text(encoding='utf-8')
            for rule in rules:
                if file.match(rule['file']):
                    if version := extract_version(content, rule['regex']):
                        print(f"Found Gradle {version} in {file.relative_to(repo_root)}")
                        gradle_version = version
                        break
            if gradle_version:
                break
        except Exception as e:
            print(f"Error reading {file.relative_to(repo_root)}: {str(e)}")
    
    if not gradle_version:
        print("No Gradle version detected in project files")
        sys.exit(1)
    
    jdk_version = find_jdk_version(gradle_version, jdk_mapping)
    print(f"\nAnalysis results for {repo_root}:")
    print(f"• Detected Gradle version: {gradle_version}")
    print(f"• Required JDK version:   {jdk_version}")

if __name__ == "__main__":
    main()
