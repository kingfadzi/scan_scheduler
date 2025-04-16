import os
import json

def detect_js_build_tool(repo_dir):

    pkg_json_path = os.path.join(repo_dir, "package.json")

    if os.path.exists(pkg_json_path):
        try:
            with open(pkg_json_path, "r") as f:
                pkg_data = json.load(f)
            if "packageManager" in pkg_data:
                pm_spec = pkg_data["packageManager"]
                if "yarn" in pm_spec:
                    return "Yarn"
                elif "pnpm" in pm_spec:
                    return "pnpm"
                elif "npm" in pm_spec:
                    return "npm"
        except Exception as e:
            self.logger.error(f"Error reading package.json: {e}")

    # Lock file detection fallback
    lock_files = {
        "yarn.lock": "Yarn",
        "pnpm-lock.yaml": "pnpm",
        "package-lock.json": "npm"
    }

    for lock_file, tool in lock_files.items():
        if os.path.exists(os.path.join(repo_dir, lock_file)):
            return tool

    # Final fallback to package.json existence
    if os.path.exists(pkg_json_path):
        return "npm"

    return None
