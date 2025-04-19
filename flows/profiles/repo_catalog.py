from prefect import flow, task, get_run_logger
import pandas as pd
from sqlalchemy import create_engine

# Set up SQLAlchemy connection to your database
DB_URL = "postgresql://postgres:postgres@localhost:5432/gitlab-usage"
engine = create_engine(DB_URL)

@task
def load_table(table_name: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql_table(table_name, conn)

@task
def fetch_all_repos() -> pd.DataFrame:
    tables = [
        "lizard_summary", "cloc_metrics",
        "trivy_vulnerability", "semgrep_results", "repo_metrics",
        "go_enry_analysis", "bitbucket_repositories"
    ]
    dfs = [load_table.fn(t)["repo_id"] for t in tables]
    repo_ids = pd.concat(dfs).drop_duplicates()
    return pd.DataFrame({"repo_id": repo_ids})

@task
def aggregate_cloc() -> pd.DataFrame:
    cloc = load_table.fn("cloc_metrics")
    return cloc[cloc["language"] != "SUM"].groupby("repo_id").agg({
        "files": "sum",
        "blank": "sum",
        "comment": "sum",
        "code": "sum"
    }).rename(columns={
        "files": "source_code_file_count",
        "blank": "total_blank",
        "comment": "total_comment",
        "code": "total_lines_of_code"
    }).reset_index()

@task
def aggregate_trivy() -> pd.DataFrame:
    df = load_table.fn("trivy_vulnerability")
    return df.groupby("repo_id").agg(
        total_trivy_vulns=("id", "count"),
        trivy_critical=("severity", lambda x: (x == "CRITICAL").sum()),
        trivy_high=("severity", lambda x: (x == "HIGH").sum()),
        trivy_medium=("severity", lambda x: (x == "MEDIUM").sum()),
        trivy_low=("severity", lambda x: (x == "LOW").sum())
    ).reset_index()

@task
def aggregate_semgrep() -> pd.DataFrame:
    df = load_table.fn("semgrep_results")
    return df.groupby("repo_id").agg(
        total_semgrep_findings=("id", "count"),
        cat_best_practice=("category", lambda x: (x == "best-practice").sum()),
        cat_compatibility=("category", lambda x: (x == "compatibility").sum()),
        cat_correctness=("category", lambda x: (x == "correctness").sum()),
        cat_maintainability=("category", lambda x: (x == "maintainability").sum()),
        cat_performance=("category", lambda x: (x == "performance").sum()),
        cat_portability=("category", lambda x: (x == "portability").sum()),
        cat_security=("category", lambda x: (x == "security").sum())
    ).reset_index()

@task
def aggregate_languages() -> pd.DataFrame:
    df = load_table.fn("go_enry_analysis")
    main = df.sort_values(["repo_id", "percent_usage"], ascending=[True, False]) \
              .drop_duplicates("repo_id")[["repo_id", "language"]] \
              .rename(columns={"language": "main_language"})
    all_langs = df.groupby("repo_id")["language"].apply(lambda x: ", ".join(sorted(set(x)))).reset_index()
    all_langs.columns = ["repo_id", "all_languages"]
    return main.merge(all_langs, on="repo_id", how="left")

@task
def load_ready_to_join_tables_full() -> dict:
    return {
        "lizard": load_table.fn("lizard_summary"),
        "repo_metrics": load_table.fn("repo_metrics"),
        "bitbucket": load_table.fn("bitbucket_repositories"),
        "component_mapping": load_table.fn("component_mapping"),
        "application_metadata": load_table.fn("application_metadata")
    }

@task
def format_app_ids(ids: pd.Series) -> str:
    unique_ids = set(filter(None, ids))
    sorted_ids = sorted(unique_ids)
    return ", ".join(sorted_ids)

def derive_app_ids(repo_df: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    version_mappings = mapping[mapping["mapping_type"] == "version_control"].copy()
    app_mappings = mapping[mapping["mapping_type"] == "business_application"][["component_id", "identifier"]].drop_duplicates()

    valid_repos = version_mappings[version_mappings["project_key"].notnull() & version_mappings["repo_slug"].notnull()]
    valid_repos["repo_id"] = valid_repos["project_key"] + "/" + valid_repos["repo_slug"]

    merged = valid_repos.merge(app_mappings, on="component_id", how="left")

    grouped = (
        merged.groupby("repo_id")["identifier"]
        .agg(format_app_ids)
        .reset_index()
        .rename(columns={"identifier": "app_id"})
    )

    return grouped

@task
def combine_all(
    all_repos, cloc, trivy, semgrep, langs, tables
):
    logger = get_run_logger()
    df = all_repos \
        .merge(cloc, on="repo_id", how="left") \
        .merge(trivy, on="repo_id", how="left") \
        .merge(semgrep, on="repo_id", how="left") \
        .merge(langs, on="repo_id", how="left") \
        .merge(tables["lizard"], on="repo_id", how="left") \
        .merge(tables["repo_metrics"], on="repo_id", how="left") \
        .merge(tables["bitbucket"], on="repo_id", how="left") \
        .merge(tables["app_metadata"], left_on="app_id", right_on="correlation_id", how="left")

        app_ids = derive_app_ids(df, tables["component_mapping"])
    df = df.merge(app_ids, on="repo_id", how="left")

    # Step 2: Join with application metadata
    df = df.merge(tables["application_metadata"], left_on="app_id", right_on="correlation_id", how="left")

    def classify(row):
        loc = row.get("total_lines_of_code", 0) or 0
        size = row.get("repo_size_bytes", 0) or 0
        if loc < 100:
            return "Non-Code -> Empty/Minimal" if size < 1_000_000 else "Non-Code -> Docs/Data"
        if size < 1_000_000:
            return "Code -> Tiny"
        if size < 10_000_000:
            return "Code -> Small"
        if size < 100_000_000:
            return "Code -> Medium"
        if size < 1_000_000_000:
            return "Code -> Large"
        return "Code -> Massive"

    df["classification_label"] = df.apply(classify, axis=1)
    logger.info(f"Final combined rows: {len(df)}")
    return df

@task
def save_to_database(df: pd.DataFrame):
    logger = get_run_logger()
    logger.info(f"Saving {len(df)} rows to table 'repo_catalog'")
    with engine.connect() as conn:
        df.to_sql("repository_catalog", conn, if_exists="replace", index=False)
    logger.info("Table 'repo_catalog' successfully written.")

from prefect.task_runners import ConcurrentTaskRunner

@flow(name="refresh_repo_catalog", task_runner=ConcurrentTaskRunner())
def refresh_repo_catalog_flow():
    all_repos = fetch_all_repos()
    cloc = aggregate_cloc()
    trivy = aggregate_trivy()
    semgrep = aggregate_semgrep()
    langs = aggregate_languages()
    tables = load_ready_to_join_tables_full()
    combined = combine_all(all_repos, cloc, trivy, semgrep, langs, tables)
    save_to_database(combined)

if __name__ == "__main__":
    refresh_repo_catalog_flow()


