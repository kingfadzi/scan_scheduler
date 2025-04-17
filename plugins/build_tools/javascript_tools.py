import os
import json
import logging
from plugins.build_tools.js_utls import detect_js_build_tool
from shared.models import Session
from shared.execution_decorator import analyze_execution
from shared.utils import Utils
from shared.base_logger import BaseLogger


class JavaScriptBuildToolAnalyzer(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)
        self.utils = Utils(logger=self.logger)

    @analyze_execution(
        session_factory=Session,
        stage="JavaScript Build Analysis",
        require_language=["JavaScript", "TypeScript"]
    )
    def run_analysis(self, repo_dir, repo):
        try:
            self.logger.debug(f"Starting analysis for repository: {repo['repo_id']}")
            self.logger.debug(f"Base directory: {repo_dir}")

            if not self.validate_repo(repo):
                return json.dumps({
                    "status": "skipped",
                    "reason": "Not a JavaScript/TypeScript project"
                })

            results = []
            for root, _, files in os.walk(repo_dir):
                if "package.json" in files:
                    self.logger.debug(f"Found package.json at: {root}")
                    result = self.analyze_directory(root, repo, repo_dir)
                    if result:
                        results.append(result)

            return json.dumps({
                "repo_id": repo['repo_id'],
                "build_tools": results,
                "count": len(results)
            }, indent=2)

        except Exception as e:
            error_msg = f"Analysis failed: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return json.dumps({"error": error_msg})

    def validate_repo(self, repo):
        repo_languages = self.utils.detect_repo_languages(repo['repo_id'])
        js_ts_present = {'JavaScript', 'TypeScript'}.intersection(repo_languages)
        self.logger.debug(f"Detected languages: {', '.join(repo_languages)}")
        return bool(js_ts_present)

    def analyze_directory(self, dir_path, repo, repo_dir):
        try:
            self.logger.debug(f"Analyzing directory: {dir_path}")

            tool = detect_js_build_tool(dir_path)
            if tool not in ['npm', 'Yarn', 'pnpm']:
                self.logger.debug(f"No supported build tool in {dir_path}")
                return None

            node_ver, tool_ver = self.extract_versions(dir_path, tool)

            rel_path = os.path.relpath(dir_path, start=repo_dir)

            self.utils.persist_build_tool(
                tool,
                repo["repo_id"],
                tool_ver,
                node_ver
            )

            result = {
                "directory": rel_path,
                "tool": tool,
                "tool_version": tool_ver,
                "node_version": node_ver
            }

            self.logger.debug(f"Build tool detected: {json.dumps(result, indent=2)}")
            return result

        except Exception as e:
            self.logger.error(f"Directory analysis error in {dir_path}: {str(e)}")
            return None

    def extract_versions(self, dir_path, tool):
        pkg_path = os.path.join(dir_path, "package.json")
        self.logger.debug(f"Extracting versions from: {pkg_path}")

        node_ver = "Unknown"
        tool_ver = "Unknown"

        if os.path.exists(pkg_path):
            try:
                with open(pkg_path) as f:
                    data = json.load(f)

                    node_ver = data.get('engines', {}).get('node', 'Unknown').strip()

                    deps = data.get('dependencies', {})
                    dev_deps = data.get('devDependencies', {})

                    tool_ver = {
                        'npm': deps.get('npm', 'bundled'),
                        'Yarn': dev_deps.get('yarn', 'Unknown'),
                        'pnpm': dev_deps.get('pnpm', 'Unknown')
                    }.get(tool, 'Unknown')

            except Exception as e:
                self.logger.error(f"Error reading {pkg_path}: {str(e)}")
        else:
            self.logger.debug("No package.json found in directory")

        return node_ver, tool_ver


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    repo_dir = "/path/to/test/repository"
    repo_data = {
        'repo_id': "test-repo-001",
        'repo_slug': "test-repo"
    }

    analyzer = JavaScriptBuildToolAnalyzer(run_id="FULL_RUN_001")

    try:
        result = analyzer.run_analysis(repo_dir, repo_data)
        print("Final Analysis Results:")
        print(result)
    except Exception as e:
        print(f"Analysis failed: {str(e)}")
