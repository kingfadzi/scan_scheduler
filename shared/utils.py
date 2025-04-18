from datetime import datetime
import time
from prefect.context import get_run_context
from sqlalchemy import text
from config.config import Config
from shared.models import Session, Repository, AnalysisExecutionLog, GoEnryAnalysis, CombinedRepoMetrics, Dependency, \
    BuildTool
from shared.query_builder import build_query
import logging
import numpy as np
from shared.base_logger import BaseLogger
import math
from pathlib import Path
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.inspection import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import asyncio
import time


class Utils(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)

    def fetch_repositories_dict(self, payload, batch_size=1000):
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

                # Convert ORM objects to dictionaries
                def serialize_repo(repo):
                    return {c.name: getattr(repo, c.name) for c in repo.__table__.columns}

                batch_dicts = [serialize_repo(repo) for repo in batch]

                yield batch_dicts
                offset += batch_size

        finally:
            session.close()
            self.logger.info(
                f"Fetch completed - Total repositories retrieved: {total_fetched:,} "
                f"over {offset//batch_size} pages"
            )
            
    def fetch_repositories_batch(self, payload, offset=0, batch_size=100, logger=None):
        if logger:
            logger.info(
                f"Fetching repository batch - Offset: {offset:,}, Size: {batch_size}, Payload keys: {list(payload.keys())}"
            )
    
        session = Session()
        base_query = build_query(payload)
    
        if logger:
            logger.debug(f"Base SQL template:\n{base_query}")
    
        try:
            final_query = f"{base_query} OFFSET {offset} LIMIT {batch_size}"
            start_time = time.perf_counter()
            batch = session.query(Repository).from_statement(text(final_query)).all()
            query_time = time.perf_counter() - start_time
    
            if logger:
                logger.info(
                    f"Fetched {len(batch)} repos in {query_time:.2f}s (offset {offset})"
                )
    
            if not batch:
                return []
    
            def serialize_repo(repo):
                return {c.name: getattr(repo, c.name) for c in repo.__table__.columns}
    
            return [serialize_repo(repo) for repo in batch]
    
        finally:
            session.close()          
            

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
            raise
        finally:
            session.close()

    def determine_final_status(self, repo: dict, run_id):
        session = None
        try:
            repo_id = repo["repo_id"]
            self.logger.info(f"Determining status for {repo['repo_name']} ({repo_id}) run_id: {run_id}")

            session = Session()

            statuses = (
                session.query(AnalysisExecutionLog.status)
                .filter(AnalysisExecutionLog.run_id == run_id, AnalysisExecutionLog.repo_id == repo_id)
                .filter(AnalysisExecutionLog.status != "PROCESSING")
                .all()
            )

            # Fetch the repository record from the database using repo_id.
            repository_record = session.query(Repository).filter(Repository.repo_id == repo_id).one_or_none()
            if not repository_record:
                self.logger.error(f"Repository record with id {repo_id} not found.")
                return

            if not statuses:
                repository_record.status = "ERROR"
                repository_record.comment = "No analysis records."
            elif any(s == "FAILURE" for (s,) in statuses):
                repository_record.status = "FAILURE"
            elif all(s == "SUCCESS" for (s,) in statuses):
                repository_record.status = "SUCCESS"
                repository_record.comment = "All steps completed."
            else:
                repository_record.status = "UNKNOWN"

            repository_record.updated_on = datetime.utcnow()
            session.add(repository_record)
            session.commit()
        except Exception as e:
            if session:
                session.rollback()
            self.logger.exception("An error occurred in determine_final_status.")
            raise
        finally:
            if session:
                session.close()


    def detect_repo_languages(self, repo_id):
        self.logger.info(f"Querying go_enry_analysis for repo_id: {repo_id}")

        session = Session()

        results = session.query(
                GoEnryAnalysis.language,
                GoEnryAnalysis.percent_usage
            ).filter(
                GoEnryAnalysis.repo_id == repo_id
            ).order_by(
                GoEnryAnalysis.percent_usage.desc()
            ).all()

        session.close()

        if results:
            main_language = [results[0].language]
            main_percent = results[0].percent_usage
            self.logger.info(
                f"Primary language for repo_id {repo_id}: {main_language} ({main_percent}%)"
            )
            return main_language

        self.logger.warning(f"No languages found in go_enry_analysis for repo_id: {repo_id}")
        return []

    def get_repo_main_language(self, repo_id: str) -> str | None:

        session = Session()

        try:
            return (
                session.query(CombinedRepoMetrics.main_language)
                .filter(CombinedRepoMetrics.repo_id == repo_id)
                .scalar()
            )
        except Exception as e:
            self.logger.error(f"Error getting main language for repo: {e}")
            raise
        finally:
            session.close()
        return None


    def persist_dependencies(self, dependencies):
        if not dependencies:
            self.logger.info("No dependencies to persist.")
            return

        try:
            self.logger.info(f"Inserting {len(dependencies)} dependencies into the database.")

            session = Session()

            dep_dicts = [
                {
                    "repo_id": dep.repo_id,
                    "name": dep.name,
                    "version": dep.version,
                    "package_type": dep.package_type,
                }
                for dep in dependencies
            ]

            ins_stmt = insert(Dependency)

            upsert_stmt = ins_stmt.on_conflict_do_nothing(
                index_elements=['repo_id', 'name', 'version']
            )


            session.execute(upsert_stmt, dep_dicts)
            session.commit()
            self.logger.info("Dependency insertion successful.")

        except Exception as e:
            session.rollback()
            self.logger.error(f"Failed to insert dependencies: {e}")
            raise
        finally:
            session.close()

    def as_dict(model):
        return {c.key: getattr(model, c.key) for c in inspect(model).mapper.column_attrs}


    def persist_build_tool(self, build_tool, repo_id_value, tool_version, runtime_version):
        try:
            self.logger.debug(
                f"Persisting versions for {repo_id_value} - build tool: {build_tool} version: {tool_version}, runtime_version: {runtime_version}"
            )
            session = Session()
            stmt = insert(BuildTool).values(
                repo_id=repo_id_value,
                tool=build_tool,
                tool_version=tool_version,
                runtime_version=runtime_version,
            ).on_conflict_do_nothing(
                index_elements=["repo_id", "tool", "tool_version", "runtime_version"]
            )
            session.execute(stmt)
            session.commit()
        except Exception as e:
            self.logger.error(f"Error persisting build tool for {repo_id_value}: {e}")
            raise
        finally:
            session.close()


    async def fetch_repositories_dict_async(self, payload, batch_size=1000):

        session = Session()
        offset = 0
        total_fetched = 0
        base_query = build_query(payload)

        try:
            while True:
                final_query = f"{base_query} OFFSET {offset} LIMIT {batch_size}"

                self.logger.debug(f"Generated query: {final_query}")

                batch = await asyncio.to_thread(
                    lambda: [
                        {c.name: getattr(r, c.name) for c in r.__table__.columns}
                        for r in session.query(Repository)
                        .from_statement(text(final_query))
                        .all()
                    ]
                )

                if not batch:
                    break

                yield batch
                offset += batch_size
                total_fetched += len(batch)

        except GeneratorExit:
            pass  # Handle async generator cancellation
        finally:
            session.close()
            self.logger.info(f"Fetched {total_fetched} repos across {offset//batch_size} pages")


def main():

    example_payload = {
        "payload": {
            "host_name": [Config.GITLAB_HOSTNAME],
           # "main_language": ["Java"]
        }
    }

    utils = Utils()

    partitions = utils.fetch_repositories_dict_async(
        payload=example_payload,
        batch_size=10,
        num_partitions=5
    )

    for idx, partition in enumerate(partitions):
        utils.logger.info(f"Processing partition {idx + 1}/{len(partitions)} with {len(partition)} repos")
        for repo in partition[:3]:
            utils.logger.info(f"Sample repo slug: {repo['repo_slug']}")

if __name__ == "__main__":
    main()
