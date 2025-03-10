import os
import json
import logging
import subprocess
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from modular.shared.models import GoEnryAnalysis, SemgrepResult, Session
from modular.shared.execution_decorator import analyze_execution
from config.config import Config
from modular.shared.base_logger import BaseLogger
import configparser
from pathlib import Path

class SemgrepAnalyzer(BaseLogger):

    def __init__(self, logger=None):
        if logger is None:
            self.logger = self.get_logger("SemgrepAnalyzer")
        else:
            self.logger = logger
        self.logger.setLevel(logging.INFO)

    @analyze_execution(session_factory=Session, stage="Semgrep Analysis")
    def run_analysis(self, repo, repo_dir, session, run_id=None):

        self.logger.info(f"Starting Semgrep analysis for repo_id: {repo.repo_id}")

        try:
            languages = self.get_languages_from_db(repo.repo_id, session)
            if not languages:
                message = f"No languages detected for repo_id: {repo.repo_id}. Skipping Semgrep scan."
                self.logger.warning(message)
                return message

            semgrep_command = self.construct_semgrep_command_specific_languages(repo_dir, languages)
            if not semgrep_command:
                message = f"No valid Semgrep rulesets found for repo_id: {repo.repo_id}. Skipping Semgrep scan."
                self.logger.warning(message)
                return message

            self.logger.info(f"Executing Semgrep command: {' '.join(semgrep_command)}")

            result = subprocess.run(
                semgrep_command,
                timeout=Config.DEFAULT_PROCESS_TIMEOUT,
                capture_output=True,
                text=True,
                check=True
            )

            semgrep_data = json.loads(result.stdout.strip())

            self.logger.debug(semgrep_data)

            findings_count = self.save_semgrep_results(session, repo.repo_id, semgrep_data)

            message = f"Semgrep analysis completed for repo_id: {repo.repo_id} with {findings_count} findings."
            self.logger.info(message)

            #return json.dumps(semgrep_data)

            return message

        except subprocess.TimeoutExpired as e:
            error_message = f"Semgrep command timed out after {e.timeout} seconds for repo {repo.repo_id}."
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        except subprocess.CalledProcessError as e:
            error_message = f"Semgrep command failed for repo_id: {repo.repo_id}. Error: {e.stderr.strip()}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

        except json.JSONDecodeError as e:
            error_message = f"Failed to parse Semgrep output for repo_id: {repo.repo_id}. Error: {str(e)}"
            self.logger.error(error_message)
            raise ValueError(error_message)

        except Exception as e:
            error_message = f"Unexpected error during Semgrep analysis for repo_id: {repo.repo_id}. Error: {str(e)}"
            self.logger.error(error_message)
            raise RuntimeError(error_message)

    def get_languages_from_db(self, repo_id, session):

        self.logger.info(f"Querying languages for repo_id: {repo_id}")
        stmt = select(GoEnryAnalysis.language).where(GoEnryAnalysis.repo_id == repo_id)
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

    def save_semgrep_results(self, session, repo_id, semgrep_data):

        self.logger.info(f"Saving Semgrep findings for repo_id: {repo_id}")
        total_upserts = 0

        for result in semgrep_data.get("results", []):
            metadata = result["extra"].get("metadata", {})
            finding = {
                "repo_id": repo_id,
                "path": result.get("path"),
                "start_line": result["start"]["line"],
                "end_line": result["end"]["line"],
                "rule_id": result.get("check_id"),
                "severity": result["extra"].get("severity"),
                "message": result["extra"].get("message"),
                "category": metadata.get("category", ""),
                "subcategory": ", ".join(metadata.get("subcategory", [])),
                "technology": ", ".join(metadata.get("technology", [])),
                "cwe": ", ".join(metadata.get("cwe", [])),
                "likelihood": metadata.get("likelihood", ""),
                "impact": metadata.get("impact", ""),
                "confidence": metadata.get("confidence", ""),
            }

            try:
                stmt = insert(SemgrepResult).values(**finding)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["repo_id", "path", "start_line", "rule_id"],
                    set_={key: stmt.excluded[key] for key in finding.keys()}
                )
                session.execute(stmt)
                total_upserts += 1
            except Exception as e:
                self.logger.error(f"Failed to upsert Semgrep finding: {finding}. Error: {e}")
                raise RuntimeError(f"Failed to upsert findings: {e}")

        session.commit()
        self.logger.info(f"Upserted {total_upserts} findings for repo_id: {repo_id}")
        return total_upserts


if __name__ == "__main__":
    repo_slug = "WebGoat"
    repo_id = "WebGoat"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug

    repo = MockRepo(repo_id=repo_id, repo_slug=repo_slug)
    repo_dir = f"/tmp/{repo.repo_slug}"
    session = Session()
    analyzer = SemgrepAnalyzer()

    try:
        analyzer.logger.info(f"Starting Semgrep analysis for repo_id: {repo.repo_id}")
        result = analyzer.run_analysis(repo, repo_dir, session, run_id="STANDALONE_RUN_001")
        analyzer.logger.info(f"Semgrep analysis result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during Semgrep analysis: {e}")
    finally:
        session.close()
        analyzer.logger.info(f"Session closed for repo_id: {repo.repo_id}")
