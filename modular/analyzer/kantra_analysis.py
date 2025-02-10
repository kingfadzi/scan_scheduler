import shutil
import os
import yaml
import subprocess
import logging
from sqlalchemy.dialects.postgresql import insert
import json

from modular.shared.base_logger import BaseLogger
from modular.shared.execution_decorator import analyze_execution
from modular.shared.models import Session, Ruleset, Violation, Label, ViolationLabel
from modular.shared.config import Config
from modular.maven.maven_helper import MavenHelper
from modular.gradle.gradle_helper import GradleHelper

class KantraAnalyzer(BaseLogger):
    def __init__(self):
        self.logger = self.get_logger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)

    @analyze_execution(session_factory=Session, stage="Kantra Analysis")
    def run_analysis(self, repo_dir, repo, session, run_id=None):
        self.logger.info(f"Starting Kantra analysis for repo_id: {repo.repo_id} ({repo.repo_slug}).")

        if not os.path.exists(repo_dir):
            raise FileNotFoundError(f"Repository directory does not exist: {repo_dir}")
        if not os.path.exists(Config.KANTRA_RULESETS):
            raise FileNotFoundError(f"Ruleset file not found: {Config.KANTRA_RULESETS}")

        maven_result = MavenHelper().generate_effective_pom(repo_dir)
        gradle_result = GradleHelper().generate_resolved_dependencies(repo_dir)

        if maven_result is None and gradle_result is None:
            self.logger.warn("Neither a valid Maven POM nor Gradle dependencies were found. Stopping Kantra analysis.")
            return "Neither a valid Maven POM nor Gradle dependencies were found."

        output_dir = os.path.join(Config.KANTRA_OUTPUT_ROOT, f"kantra_output_{repo.repo_slug}")
        os.makedirs(output_dir, exist_ok=True)

        command = self.build_kantra_command(repo_dir, output_dir)
        self.logger.info(f"Executing Kantra command: {command}")

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                check=True,
                timeout=Config.DEFAULT_PROCESS_TIMEOUT
            )
            self.logger.info(f"Kantra analysis completed for repo_id: {repo.repo_id}")

            output_yaml_path = os.path.join(output_dir, "output.yaml")
            analysis_data = self.parse_output_yaml(output_yaml_path)
            self.save_kantra_results(session, repo.repo_id, analysis_data)
            self.logger.info(f"Kantra results persisted for repo_id: {repo.repo_id}")

        except subprocess.CalledProcessError as e:
            handle_subprocess_error(e, self.logger, command)
        except subprocess.TimeoutExpired as e:
            self.logger.error(f"Kantra command timed out after {e.timeout} seconds: {e}")
            raise RuntimeError("Kantra command timed out.")
        except Exception as e:
            error_message = f"Unexpected error during Kantra analysis: {e}"
            self.logger.error(error_message)
            raise
        finally:
            if os.path.exists(output_dir):
                shutil.rmtree(output_dir, ignore_errors=True)
                self.logger.info(f"Deleted Kantra output directory to save space: {output_dir}")

        return json.dumps(analysis_data)

    def build_kantra_command(self, repo_dir, output_dir):
        return (
            f"kantra analyze "
            f"--input={repo_dir} "
            f"--output={output_dir} "
            f"--rules={os.path.abspath(Config.KANTRA_RULESETS)} "
            f"--enable-default-rulesets=false "
            f"--overwrite"
        )

    def parse_output_yaml(self, yaml_file):
        if not os.path.isfile(yaml_file):
            self.logger.warning(f"Output YAML file not found: {yaml_file}")
            return None
        try:
            with open(yaml_file, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.logger.error(f"Error reading/parsing YAML file {yaml_file}: {e}")
            return None

    def save_kantra_results(self, session, repo_id, analysis_data):
        self.logger.debug(f"Processing Kantra results for repo_id: {repo_id}")
        if not analysis_data:
            self.logger.warning("No data found to persist. Skipping database updates.")
            return
        try:
            for ruleset_data in analysis_data:
                ruleset_name = ruleset_data.get("name")
                description = ruleset_data.get("description")
                session.execute(
                    insert(Ruleset)
                    .values(name=ruleset_name, description=description)
                    .on_conflict_do_update(
                        index_elements=["name"],
                        set_={"description": description}
                    )
                )
                for rulename, violation_data in ruleset_data.get("violations", {}).items():
                    if not violation_data or not violation_data.get("description"):
                        continue
                    violation_desc = violation_data["description"]
                    category = violation_data.get("category")
                    effort = violation_data.get("effort")
                    viol_stmt = (
                        insert(Violation)
                        .values(
                            repo_id=repo_id,
                            ruleset_name=ruleset_name,
                            rule_name=rulename,
                            description=violation_desc,
                            category=category,
                            effort=effort
                        )
                        .on_conflict_do_update(
                            index_elements=["repo_id", "ruleset_name", "rule_name", "description"],
                            set_={"category": category, "effort": effort}
                        )
                        .returning(Violation.id)
                    )
                    viol_result = session.execute(viol_stmt)
                    violation_id = viol_result.scalar()
                    if violation_id is None:
                        existing_vio = (
                            session.query(Violation)
                            .filter_by(
                                repo_id=repo_id,
                                ruleset_name=ruleset_name,
                                rule_name=rulename,
                                description=violation_desc
                            )
                            .one()
                        )
                        violation_id = existing_vio.id
                    labels = violation_data.get("labels", [])
                    for label_str in labels:
                        if "=" not in label_str:
                            self.logger.warning(f"Skipping invalid label format: {label_str}")
                            continue
                        key, value = label_str.split("=", 1)
                        lbl_stmt = (
                            insert(Label)
                            .values(key=key, value=value)
                            .on_conflict_do_nothing(index_elements=["key", "value"])
                            .returning(Label.id)
                        )
                        lbl_result = session.execute(lbl_stmt)
                        label_id = lbl_result.scalar()
                        if label_id is None:
                            existing_lbl = (
                                session.query(Label)
                                .filter_by(key=key, value=value)
                                .one()
                            )
                            label_id = existing_lbl.id
                        link_stmt = (
                            insert(ViolationLabel)
                            .values(violation_id=violation_id, label_id=label_id)
                            .on_conflict_do_nothing(index_elements=["violation_id", "label_id"])
                        )
                        session.execute(link_stmt)
                        session.commit()
            self.logger.debug(f"Kantra results committed for repo_id: {repo_id}")
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error saving Kantra results for repo_id {repo_id}: {e}")
            raise


def handle_subprocess_error(e, logger, command):
    msg = [
        f"Subprocess command failed with exit code {e.returncode}.",
        f"Command: {command}"
    ]
    if e.stdout:
        msg.append(f"Stdout:\n{e.stdout.strip()}")
    if e.stderr:
        msg.append(f"Stderr:\n{e.stderr.strip()}")
    full_msg = "\n".join(msg)
    logger.error(full_msg)
    raise RuntimeError(full_msg) from e


if __name__ == "__main__":
    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug

    analyzer = KantraAnalyzer()
    mock_repo_id = "sonar-metrics"
    mock_repo_slug = "sonar-metrics"
    mock_repo_dir = "/Users/fadzi/tools/gradle_projects/sonar-metrics"

    from modular.shared.models import Session
    try:
        session = Session()
    except Exception as e:
        analyzer.logger.error(f"Failed to initialize database session: {e}")
        session = None

    repo = MockRepo(mock_repo_id, mock_repo_slug)
    if session is None:
        analyzer.logger.warning("Session is None. Skipping DB-related operations.")

    try:
        analyzer.run_analysis(
            repo_dir=mock_repo_dir,
            repo=repo,
            session=session,
            run_id="STANDALONE_RUN_001"
        )
    except Exception as e:
        analyzer.logger.error(f"Error during standalone Kantra analysis: {e}")
