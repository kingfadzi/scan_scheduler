import os
import json
from sqlalchemy.dialects.postgresql import insert
import logging
from plugins.javascript.javascript_dependencies import JavaScriptDependencyAnalyzer
from plugins.javascript.js_utls import detect_js_build_tool
from shared.language_required_decorator import language_required
from shared.models import Session, BuildTool
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
            self.logger.info(
                f"Starting JavaScript build analysis for repo_id: {repo['repo_id']} (repo slug: {repo['repo_slug']})."
            )

            js_build_tool = self.validate_repo_and_tool(repo_dir, repo)
            if js_build_tool not in ['npm', 'Yarn', 'pnpm']:
                return js_build_tool

            node_version, tool_version = self.extract_versions(repo_dir, js_build_tool)
            self.logger.info(
                f"Detected {js_build_tool}. Version: {tool_version}, Node.js version: {node_version}"
            )

            self.utils.persist_build_tool(js_build_tool, repo["repo_id"], tool_version, node_version)

            result = {
                "repo_id": repo['repo_id'],
                "tool": js_build_tool,
                "tool_version": tool_version,
                "runtime_version": node_version,
            }
            self.logger.info("JavaScript build analysis completed.")
            return json.dumps(result)

        except Exception as e:
            self.logger.exception(f"Error during run_analysis for repo_id {repo['repo_id']}: {e}")
            raise


    def validate_repo_and_tool(self, repo_dir, repo):

        repo_languages = self.utils.detect_repo_languages(repo['repo_id'])
        if not {'JavaScript', 'TypeScript'}.intersection(repo_languages):
            message = f"Repo {repo['repo_id']} is not a JavaScript/TypeScript project. Skipping."
            self.logger.info(message)
            return message

        js_build_tool = detect_js_build_tool(repo_dir)
        if js_build_tool not in ['npm', 'Yarn', 'pnpm']:
            message = f"Repo {repo['repo_id']} is JavaScript but doesn't use npm/Yarn/pnpm. Skipping."
            self.logger.info(message)
            return message

        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.error(error_message)
            raise FileNotFoundError(error_message)

        return js_build_tool


    def extract_versions(self, repo_dir, js_build_tool):
        package_json_path = os.path.join(repo_dir, "package.json")
        node_version = "Unknown"
        tool_version = "Unknown"

        if os.path.exists(package_json_path):
            try:
                with open(package_json_path) as f:
                    package_data = json.load(f)
                    engines = package_data.get('engines', {})
                    if 'node' in engines:
                        node_version = engines['node'].strip()

                    if js_build_tool == 'npm':
                        tool_version = package_data.get('dependencies', {}).get('npm', 'bundled')
                    elif js_build_tool == 'Yarn':
                        tool_version = package_data.get('devDependencies', {}).get('yarn', 'Unknown')
                    elif js_build_tool == 'pnpm':
                        tool_version = package_data.get('devDependencies', {}).get('pnpm', 'Unknown')

            except Exception as e:
                self.logger.error(f"Error parsing package.json: {e}")

        return node_version, tool_version


if __name__ == "__main__":
    import logging
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    repo_dir = "/tmp/VulnerableApp"
    repo_id = "vulnerable-apps/VulnerableApp"
    repo_slug = "VulnerableApp"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug
            self.repo_name = repo_slug

    repo = MockRepo(repo_id, repo_slug)

    # Dummy session object; adjust or replace with your actual session management if needed.
    class Session:
        def close(self):
            pass

    session = Session()
    helper = JavaScriptDependencyAnalyzer()

    try:
        dependencies = helper.run_analysis(repo_dir, repo)
        helper.logger.info(f"Standalone JavaScript analysis result: {dependencies}")
        for dep in dependencies:
            print(f"Dependency: {dep.name} - {dep.version} (Repo ID: {dep.repo_id})")
    except Exception as e:
        helper.logger.error(f"Error during standalone JavaScript analysis: {e}")
    finally:
        session.close()
