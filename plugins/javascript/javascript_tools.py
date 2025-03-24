import os
import json
import logging
from sqlalchemy.dialects.postgresql import insert
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
            self.logger.info(f"Starting analysis for {repo['repo_id']}")
            
            if not self.validate_repo(repo):
                return json.dumps({"status": "skipped", "reason": "Not JS/TS project"})

            results = []
            for root, _, files in os.walk(repo_dir):
                if "package.json" in files:
                    result = self.analyze_directory(root, repo)
                    if result:
                        results.append(result)

            return json.dumps({
                "repo_id": repo['repo_id'],
                "build_tools": results,
                "count": len(results)
            })

        except Exception as e:
            error_msg = f"Analysis failed: {str(e)}"
            self.logger.error(error_msg)
            return json.dumps({"error": error_msg})

    def validate_repo(self, repo):
        repo_languages = self.utils.detect_repo_languages(repo['repo_id'])
        return bool({'JavaScript', 'TypeScript'}.intersection(repo_languages))

    def analyze_directory(self, dir_path, repo):
        try:
            tool = detect_js_build_tool(dir_path)
            if tool not in ['npm', 'Yarn', 'pnpm']:
                return None

            node_ver, tool_ver = self.extract_versions(dir_path, tool)
            rel_path = os.path.relpath(dir_path, repo['repo_dir'])

            self.utils.persist_build_tool(tool, repo["repo_id"], tool_ver, node_ver)

            return {
                "directory": rel_path,
                "tool": tool,
                "tool_version": tool_ver,
                "node_version": node_ver
            }
        except Exception as e:
            self.logger.error(f"Directory {dir_path} error: {e}")
            return None

    def extract_versions(self, dir_path, tool):
        pkg_path = os.path.join(dir_path, "package.json")
        node_ver = tool_ver = "Unknown"

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
                self.logger.error(f"Error reading {pkg_path}: {e}")

        return node_ver, tool_ver


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Test configuration
    repo_dir = "/path/to/repo"
    repo_data = {
        'repo_id': "test-repo-123",
        'repo_slug': "test-repo",
        'repo_dir': repo_dir
    }

    analyzer = JavaScriptBuildToolAnalyzer(run_id="JSON_RUN_001")
    
    try:
        result_json = analyzer.run_analysis(repo_dir, repo_data)
        print("Analysis Result (raw JSON string):")
        print(result_json)
        
        # To work with the data as Python objects:
        result_data = json.loads(result_json)
        print("\nFormatted Results:")
        print(f"Repo ID: {result_data['repo_id']}")
        print(f"Found {result_data['count']} build configurations:")
        for config in result_data['build_tools']:
            print(f"- {config['directory']}: {config['tool']} {config['tool_version']}")
            
    except Exception as e:
        print(f"Analysis failed: {str(e)}")