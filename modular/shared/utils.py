import logging
from datetime import datetime
import time
import os
from prefect.context import get_run_context
from sqlalchemy import text
from config.config import Config
from modular.shared.models import Session, Repository, AnalysisExecutionLog, GoEnryAnalysis, CombinedRepoMetrics
from modular.shared.query_builder import build_query
import logging
import numpy as np
from modular.shared.base_logger import BaseLogger
import math
from pathlib import Path


class Utils(BaseLogger):

    def __init__(self, logger=None):
        if logger is None:
            self.logger = self.get_logger("Utils")
        else:
            self.logger = logger
        self.logger.setLevel(logging.DEBUG)

    def create_batches(self, payload, batch_size=1000):
        self.logger.info(f"Starting batch creation - Target batch size: {batch_size}")

        all_repos = []
        for batch in self.fetch_repositories(payload, batch_size):
            all_repos.extend(batch)
            self.logger.debug(
                f"Accumulated {len(batch)} repos in current batch, "
                f"Total so far: {len(all_repos)}"
            )

        total_repos = len(all_repos)
        self.logger.info(f"Total repositories fetched: {total_repos}")

        num_partitions = max(1, math.ceil(total_repos / batch_size))

        partitions = np.array_split(all_repos, num_partitions)
        partition_sizes = [len(p) for p in partitions]

        self.logger.info(
            f"Created {num_partitions} partitions with sizes: {partition_sizes} "
            f"(Standard deviation: {np.std(partition_sizes):.1f})"
        )

        return partitions

    def fetch_repositories(self, payload, batch_size=1000):

        self.logger.info(
            f"Initializing repository fetch - Payload: {payload.keys()}, "
            f"Page size: {batch_size}"
        )

        session = Session()
        offset = 0
        total_fetched = 0
        base_query = build_query(payload)

        self.logger.debug(f"Base SQL template:\n{base_query}")

        try:
            while True:
                final_query = f"{base_query} OFFSET {offset} LIMIT {batch_size}"
                self.logger.info(
                    f"Executing paginated query - Offset: {offset:,}, "
                    f"Limit: {batch_size}"
                )

                start_time = time.perf_counter()
                batch = session.query(Repository).from_statement(text(final_query)).all()
                query_time = time.perf_counter() - start_time

                batch_size_actual = len(batch)
                total_fetched += batch_size_actual

                self.logger.debug(
                    f"Query completed in {query_time:.2f}s - "
                    f"Returned {batch_size_actual} results\n"
                    f"Sample results: {[r.repo_slug[:20] for r in batch[:3]]}..."
                )

                if not batch:
                    self.logger.info("Empty result set - Ending pagination")
                    break

                detach_start = time.perf_counter()
                for repo in batch:
                    _ = repo.repo_slug  # Force attribute load
                    session.expunge(repo)
                self.logger.debug(f"Detachment completed in {time.perf_counter() - detach_start:.2f}s")

                yield batch
                offset += batch_size

        finally:
            session.close()
            self.logger.info(
                f"Fetch completed - Total repositories retrieved: {total_fetched:,} "
                f"over {offset//batch_size} pages"
            )


    def refresh_views(self):

        views_to_refresh = [
            "combined_repo_metrics",
            "combined_repo_violations",
            "combined_repo_metrics_api",
            "app_component_repo_mapping",
        ]

        session = Session()
        try:
            for view in views_to_refresh:
                self.logger.info(f"Refreshing materialized view: {view}")
                session.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}"))

            session.commit()
            self.logger.info("All materialized views refreshed successfully.")
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error refreshing materialized views: {e}")
        finally:
            session.close()

    def determine_final_status(self, repo, run_id, session):

        self.logger.info(f"Determining status for {repo.repo_name} ({repo.repo_id}) run_id: {run_id}")
        statuses = (
            session.query(AnalysisExecutionLog.status)
            .filter(AnalysisExecutionLog.run_id == run_id, AnalysisExecutionLog.repo_id == repo.repo_id)
            .filter(AnalysisExecutionLog.status != "PROCESSING")
            .all()
        )

        if not statuses:
            repo.status = "ERROR"
            repo.comment = "No analysis records."
        elif any(s == "FAILURE" for (s,) in statuses):
            repo.status = "FAILURE"
        elif all(s == "SUCCESS" for (s,) in statuses):
            repo.status = "SUCCESS"
            repo.comment = "All steps completed."
        else:
            repo.status = "UNKNOWN"

        repo.updated_on = datetime.utcnow()
        session.add(repo)
        session.commit()

    @staticmethod
    def generate_repo_flow_run_name():
        run_ctx = get_run_context()
        repo_slug = run_ctx.flow_run.parameters.get("repo_slug")
        return f"{repo_slug}"

    @staticmethod
    def generate_main_flow_run_name():
        run_ctx = get_run_context()
        start_time = run_ctx.flow_run.expected_start_time
        formatted_time = start_time.strftime('%Y-%m-%d %H:%M:%S')
        return f"{formatted_time}"

    @staticmethod
    def generate_partition_run_name():
        from prefect.runtime import flow_run
        params = flow_run.parameters
        prefix = params.get("flow_prefix", "partition")
        idx = params.get("partition_idx", 0)
        return f"{prefix}-partition-{idx}"

    def detect_repo_languages(self, repo_id, session):
        self.logger.info(f"Querying go_enry_analysis for repo_id: {repo_id}")

        results = session.query(
                GoEnryAnalysis.language,
                GoEnryAnalysis.percent_usage
            ).filter(
                GoEnryAnalysis.repo_id == repo_id
            ).order_by(
                GoEnryAnalysis.percent_usage.desc()
            ).all()

        if results:
            main_language = [results[0].language]
            main_percent = results[0].percent_usage
            self.logger.info(
                f"Primary language for repo_id {repo_id}: {main_language} ({main_percent}%)"
            )
            return main_language

        self.logger.warning(f"No languages found in go_enry_analysis for repo_id: {repo_id}")
        return []

    def get_repo_main_language(self, repo_id: str, session) -> str | None:

        try:
            return (
                session.query(CombinedRepoMetrics.main_language)
                .filter(CombinedRepoMetrics.repo_id == repo_id)
                .scalar()
            )
        except Exception as e:
            self.logger.error(f"Error getting main language for repo: {e}")
        finally:
            session.close()
        return None

    def detect_java_build_tool(self, repo_dir):
        EXCLUDE_DIRS = {'.gradle', 'build', 'out', 'target', '.git', '.idea', '.settings'}
        gradle_files = {"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}

        maven_pom = False
        found_gradle_files = set()

        repo_path = Path(repo_dir).resolve()

        for path in repo_path.rglob('*'):
            if any(part in EXCLUDE_DIRS for part in path.parts):
                continue

            if path.is_file():
                if path.name == "pom.xml":
                    maven_pom = True
                    self.logger.debug(f"Found Maven POM at: {path.relative_to(repo_path)}")

                if path.name in gradle_files:
                    found_gradle_files.add(path.name)
                    self.logger.debug(f"Found Gradle file at: {path.relative_to(repo_path)}")

        gradle_found = len(found_gradle_files) > 0
        conflict = maven_pom and gradle_found

        if conflict:
            self.logger.warning(
                f"Build tool conflict detected in {repo_path.name}\n"
                f"Maven POMs: {maven_pom}\n"
                f"Gradle files: {', '.join(found_gradle_files)}"
            )
            return "Maven"
        elif maven_pom:
            self.logger.info(f"Detected Maven project in {repo_path.name}")
            return "Maven"
        elif gradle_found:
            self.logger.info(
                f"Detected Gradle project in {repo_path.name}\n"
                f"Found files: {', '.join(found_gradle_files)}"
            )
            return "Gradle"

        self.logger.debug(
            f"No Java build system detected in {repo_path.name}\n"
            f"Searched paths: {repo_path}\n"
            f"Excluded directories: {', '.join(EXCLUDE_DIRS)}"
        )
        return None


def main():

    example_payload = {
        "payload": {
            "host_name": [Config.GITLAB_HOSTNAME],
           # "main_language": ["Java"]
        }
    }

    utils = Utils()

    partitions = utils.create_batches(
        payload=example_payload,
        batch_size=10,
        num_partitions=5
    )

    for idx, partition in enumerate(partitions):
        utils.logger.info(f"Processing partition {idx + 1}/{len(partitions)} with {len(partition)} repos")
        for repo in partition[:3]:
            utils.logger.info(f"Sample repo slug: {repo.repo_slug}")

if __name__ == "__main__":
    main()
