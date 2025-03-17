#!/usr/bin/env python3
from pathlib import Path
import re
import yaml
import argparse
import sys
from typing import Optional, List

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
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable debug output'
    )
    return parser.parse_args()

def find_gradle_files(root: Path, verbose: bool = False) -> List[Path]:
    """Locate Gradle configuration files with improved detection"""
    gradle_files = []
    
    for path in root.rglob('*'):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            if verbose:
                print(f"Skipping excluded path: {path}")
            continue
            
        if not path.is_file():
            continue

        # Match build configuration files
        if path.name in {'build.gradle', 'build.gradle.kts'}:
            gradle_files.append(path)
            if verbose:
                print(f"Found build file: {path}")
        # Match settings files
        elif path.name in {'settings.gradle', 'settings.gradle.kts'}:
            gradle_files.append(path)
            if verbose:
                print(f"Found settings file: {path}")
        # Match wrapper properties
        elif path.name == 'gradle-wrapper.properties' and 'gradle/wrapper' in path.parts:
            gradle_files.append(path)
            if verbose:
                print(f"Found wrapper properties: {path}")
        # Match gradle.properties
        elif path.name == 'gradle.properties':
            gradle_files.append(path)
            if verbose:
                print(f"Found gradle.properties: {path}")
    
    # Prioritize wrapper properties first
    return sorted(gradle_files, key=lambda p: 0 if 'wrapper' in p.parts else 1)

def extract_version(content: str, pattern: str) -> Optional[str]:
    """Extract and normalize Gradle version with debug"""
    try:
        if match := re.search(pattern, content):
            version = match.group(1).split('-')[0]
            return version
    except Exception as e:
        print(f"Regex error: {str(e)}")
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
    config_errors = False
    if not GRADLE_RULES_FILE.exists():
        print(f"Error: Missing rules file at {GRADLE_RULES_FILE}")
        config_errors = True
    if not JDK_MAPPING_FILE.exists():
        print(f"Error: Missing JDK mapping at {JDK_MAPPING_FILE}")
        config_errors = True
    if config_errors:
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

    # Find and process files
    found_files = find_gradle_files(repo_root, args.verbose)
    
    if args.verbose:
        print(f"\nFound {len(found_files)} potential Gradle files:")
        for f in found_files:
            print(f"  - {f.relative_to(repo_root)}")

    if not found_files:
        print("No Gradle configuration files found")
        sys.exit(1)

    gradle_version = None
    for file in found_files:
        try:
            content = file.read_text(encoding='utf-8')
            if args.verbose:
                print(f"\nChecking file: {file.relative_to(repo_root)}")
                
            for rule in rules:
                try:
                    if file.match(rule['file']):
                        if args.verbose:
                            print(f" Applying rule: {rule['regex']}")
                            
                        if version := extract_version(content, rule['regex']):
                            print(f"Found Gradle {version} in {file.relative_to(repo_root)}")
                            gradle_version = version
                            break
                except Exception as e:
                    print(f"Rule error: {str(e)}")
                    continue
                
            if gradle_version:
                break
        except Exception as e:
            print(f"Error reading {file.relative_to(repo_root)}: {str(e)}")

    if not gradle_version:
        print("\nNo Gradle version detected. Possible reasons:")
        print("- Version not declared in standard locations")
        print("- Version format doesn't match regex patterns")
        print("- Missing gradle-wrapper.properties file")
        print("\nChecked files:")
        for f in found_files:
            print(f"  - {f.relative_to(repo_root)}")
        sys.exit(1)
    
    jdk_version = find_jdk_version(gradle_version, jdk_mapping)
    print(f"\nAnalysis results for {repo_root}:")
    print(f"• Detected Gradle version: {gradle_version}")
    print(f"• Required JDK version:   {jdk_version}")

if __name__ == "__main__":
    main()
