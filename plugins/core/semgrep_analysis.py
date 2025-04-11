import os
import json
import logging
import subprocess
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from shared.models import GoEnryAnalysis, SemgrepResult, Session
from shared.execution_decorator import analyze_execution
from config.config import Config
from shared.base_logger import BaseLogger
import configparser
from pathlib import Path
import psutil

class SemgrepAnalyzer(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)

    @analyze_execution(session_factory=Session, stage="Semgrep Analysis")
    def run_analysis(self, repo, repo_dir):

        self.logger.info(f"Starting Semgrep analysis for repo_id: {repo['repo_id']}")

        try:
            languages = self.get_languages_from_db(repo['repo_id'])
            if not languages:
                message = f"No languages detected for repo_id: {repo['repo_id']}. Skipping Semgrep scan."
                self.logger.warning(message)
                return message

            semgrep_command = self.construct_semgrep_command_specific_languages(repo_dir, languages)
            if not semgrep_command:
                message = f"No valid Semgrep rulesets found for repo_id: {repo['repo_id']}. Skipping Semgrep scan."
                self.logger.warning(message)
                return message

            self.logger.info(f"Executing Semgrep command: {' '.join(semgrep_command)}")

            try:
                result = subprocess.run(
                    semgrep_command,
                    #timeout=Config.DEFAULT_PROCESS_TIMEOUT,
                    timeout=180,
                    capture_output=True,
                    text=True,
                    check=True
                )
            except subprocess.TimeoutExpired as e:
                parent = psutil.Process(e.process.pid)
                for child in parent.children(recursive=True):
                    child.kill()
                parent.kill()

            semgrep_data = json.loads(result.stdout.strip())

            self.logger.debug(semgrep_data)

            findings_count = self.save_semgrep_results(repo['repo_id'], semgrep_data)

            message = f"Semgrep analysis completed for repo_id: {repo['repo_id']} with {findings_count} findings."
            self.logger.info(message)

            return message

        except subprocess.TimeoutExpired as e:
            error_message = f"Semgrep command timed out after {e.timeout} seconds for repo {repo['repo_id']}."
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        except subprocess.CalledProcessError as e:
            error_message = f"Semgrep command failed for repo_id: {repo['repo_id']}. Error: {e.stderr.strip()}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        except json.JSONDecodeError as e:
            error_message = f"Failed to parse Semgrep output for repo_id: {repo['repo_id']}. Error: {str(e)}"
            self.logger.error(error_message)
            raise ValueError(error_message)

        except Exception as e:
            error_message = f"Unexpected error during Semgrep analysis for repo_id: {repo['repo_id']}. Error: {str(e)}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

    def get_languages_from_db(self, repo_id):

        self.logger.info(f"Querying languages for repo_id: {repo_id}")
        stmt = select(GoEnryAnalysis.language).where(GoEnryAnalysis.repo_id == repo_id)
        session = Session()
        result = session.execute(stmt).fetchall()
        return [row.language for row in result] if result else []


    def construct_semgrep_command(self, repo_dir):
        rules_dir = os.path.abspath(Config.SEMGREP_RULES)

        if not os.path.exists(rules_dir):
            self.logger.error(f"Semgrep rules directory not found: {rules_dir}")
            return None

        command = ["semgrep", "--experimental", "--json", "--skip-unknown", repo_dir, "--verbose"]
        return command


    def construct_semgrep_command_specific_languages(self, repo_dir, languages):

        project_root = Path(__file__).resolve().parent.parent.parent
        config_dir = project_root / Config.SEMGREP_CONFIG_DIR

        ruleset_dir = os.path.abspath(Config.SEMGREP_RULES)

        config = configparser.ConfigParser()
        config_file = os.path.join(config_dir, "config.ini")
        if not os.path.exists(config_file):
            self.logger.error(f"Configuration file not found: {config_file}")
            return None
        config.read(config_file)
        rulesets = []
        for lang in languages:
            lang_lower = lang.lower()
            try:
                relative_path = config.get(lang_lower, 'path')
                ruleset_path = os.path.join(ruleset_dir, relative_path)
                if os.path.exists(ruleset_path):
                    rulesets.append(ruleset_path)
                    self.logger.info(f"Found Semgrep ruleset for language '{lang}': {ruleset_path}")
                else:
                    self.logger.warning(f"Semgrep ruleset for language '{lang}' does not exist at {ruleset_path}. Skipping.")
            except (configparser.NoSectionError, configparser.NoOptionError) as e:
                self.logger.warning(f"Configuration error for language '{lang}': {e}. Skipping.")
        if not rulesets:
            self.logger.warning(f"No valid Semgrep rulesets found for the detected languages: {languages}. Skipping.")
            return None
        command = ["semgrep", "--experimental", "--json", "--skip-unknown", repo_dir, "--verbose"]
        for ruleset in rulesets:
            command.extend(["--config", ruleset])
        return command

    def save_semgrep_results(self, repo_id, semgrep_data):
        session = Session()
        total_upserts = 0
        try:
            session.query(SemgrepResult).filter(
                SemgrepResult.repo_id == repo_id
            ).delete()

            for result in semgrep_data.get("results", []):
                metadata = result["extra"].get("metadata", {})
                finding = SemgrepResult(
                    repo_id=repo_id,
                    path=result.get("path"),
                    start_line=result["start"]["line"],
                    end_line=result["end"]["line"],
                    rule_id=result.get("check_id"),
                    severity=result["extra"].get("severity"),
                    message=result["extra"].get("message"),
                    category=metadata.get("category", ""),
                    subcategory=", ".join(metadata.get("subcategory", [])),
                    technology=", ".join(metadata.get("technology", [])),
                    cwe=", ".join(metadata.get("cwe", [])),
                    likelihood=metadata.get("likelihood", ""),
                    impact=metadata.get("impact", ""),
                    confidence=metadata.get("confidence", "")
                )
                session.add(finding)
                total_upserts += 1

            session.commit()
            self.logger.info(f"Upserted {total_upserts} findings for repo_id: {repo_id}")
            return total_upserts
        except Exception as e:
            session.rollback()
            self.logger.error(f"Failed to save Semgrep findings for repo_id {repo_id}. Error: {e}")
            raise
        finally:
            session.close()



if __name__ == "__main__":
    repo_slug = "WebGoat"
    repo_id = "WebGoat"

    # Changed to dictionary
    repo = {
        'repo_id': repo_id,
        'repo_slug': repo_slug
    }

    repo_dir = f"/tmp/{repo['repo_slug']}"
    session = Session()
    analyzer = SemgrepAnalyzer()

    try:
        analyzer.logger.info(f"Starting Semgrep analysis for repo_id: {repo['repo_id']}")
        result = analyzer.run_analysis(repo, repo_dir, session)
        analyzer.logger.info(f"Semgrep analysis result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during Semgrep analysis: {e}")
    finally:
        session.close()
        analyzer.logger.info(f"Session closed for repo_id: {repo['repo_id']}")

