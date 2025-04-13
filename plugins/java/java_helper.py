from pathlib import Path
import os

EXCLUDE_DIRS = {'.gradle', 'build', 'out', 'target', '.git', '.idea', '.settings', 'bin'}

def is_gradle_project(repo_dir: str) -> bool:
    repo_path = Path(repo_dir)
    for path in repo_path.rglob("build.gradle*"):
        if not any(part in EXCLUDE_DIRS for part in path.parts):
            return True
    return False

def has_gradle_lockfile(repo_dir: str) -> bool:
    return os.path.exists(os.path.join(repo_dir, "gradle.lockfile"))

def is_maven_project(repo_dir: str) -> bool:
    return os.path.exists(os.path.join(repo_dir, "pom.xml"))

