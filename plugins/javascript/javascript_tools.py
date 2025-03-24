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
            self.logger.debug(f"Starting build tool analysis for repository: {repo['repo_id']}")
            self.logger.debug(f"Scanning directory: {repo_dir}")

            if not self.validate_repo(repo):
                skip_reason = "Repository is not a JavaScript/TypeScript project"
                self.logger.debug(skip_reason)
                return json.dumps({"status": "skipped", "reason": skip_reason})

            results = []
            for root, _, files in os.walk(repo_dir):
                if "package.json" in files:
                    self.logger.debug(f"Found package.json in: {root}")
                    result = self.analyze_directory(root, repo)
                    if result:
                        results.append(result)
                        self.logger.debug(f"Build tool detected in {result['directory']}:")
                        self.logger.debug(f"  Tool: {result['tool']}")
                        self.logger.debug(f"  Version: {result['tool_version']}")
                        self.logger.debug(f"  Node.js: {result['node_version']}")

            self.logger.debug(f"Analysis completed. Total configurations found: {len(results)}")
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
        self.logger.debug(f"Detected languages: {', '.join(repo_languages)}")
        return bool({'JavaScript', 'TypeScript'}.intersection(repo_languages))

    def analyze_directory(self, dir_path, repo):
        try:
            self.logger.debug(f"Analyzing directory: {dir_path}")
            tool = detect_js_build_tool(dir_path)
            
            if tool not in ['npm', 'Yarn', 'pnpm']:
                self.logger.debug(f"No supported build tool detected in {dir_path}")
                return None

            node_ver, tool_ver = self.extract_versions(dir_path, tool)
            rel_path = os.path.relpath(dir_path, repo['repo_dir'])

            self.logger.debug(f"Persisting build tool data for {rel_path}")
            self.utils.persist_build_tool(tool, repo["repo_id"], tool_ver, node_ver)

            return {
                "directory": rel_path,
                "tool": tool,
                "tool_version": tool_ver,
                "node_version": node_ver
            }
        except Exception as e:
            self.logger.error(f"Directory analysis failed for {dir_path}: {str(e)}")
            return None

    def extract_versions(self, dir_path, tool):
        pkg_path = os.path.join(dir_path, "package.json")
        self.logger.debug(f"Extracting versions from: {pkg_path}")
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

                self.logger.debug(f"Parsed versions - Node: {node_ver}, {tool}: {tool_ver}")
            except Exception as e:
                self.logger.error(f"Error reading package.json: {str(e)}")
        else:
            self.logger.debug("No package.json found in directory")

        return node_ver, tool_ver


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    repo_dir = "/path/to/repo"
    repo_data = {
        'repo_id': "test-repo-123",
        'repo_slug': "test-repo",
        'repo_dir': repo_dir
    }

    analyzer = JavaScriptBuildToolAnalyzer(run_id="DEBUG_RUN_001")
    
    try:
        self.logger.debug("Starting standalone analysis")
        result_json = analyzer.run_analysis(repo_dir, repo_data)
        
        self.logger.debug("Raw JSON output:")
        self.logger.debug(result_json)
        
        self.logger.debug("Formatted results:")
        result_data = json.loads(result_json)
        if 'build_tools' in result_data:
            for config in result_data['build_tools']:
                self.logger.debug(f"Directory: {config['directory']}")
                self.logger.debug(f"  Build Tool: {config['tool']} {config['tool_version']}")
                self.logger.debug(f"  Node.js Version: {config['node_version']}")
                
    except Exception as e:
        self.logger.error(f"Standalone analysis failed: {str(e)}")