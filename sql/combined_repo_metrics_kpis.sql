DROP MATERIALIZED VIEW IF EXISTS combined_repo_metrics_api;

CREATE MATERIALIZED VIEW combined_repo_metrics_api AS
SELECT
    repo_id,
    host_name,
    project_key,
    repo_slug,
    activity_status,
    classification_label,
    main_language,
    all_languages,
    app_id,
    tc,
    total_lines_of_code,
    total_commits,
    avg_cyclomatic_complexity,
    number_of_contributors,
    repo_size_bytes,
    last_commit_date,
    updated_at
FROM combined_repo_metrics
ORDER BY repo_id;

CREATE INDEX ON combined_repo_metrics_api (host_name);
CREATE INDEX ON combined_repo_metrics_api (activity_status);
CREATE INDEX ON combined_repo_metrics_api (tc);
CREATE INDEX ON combined_repo_metrics_api (main_language);
CREATE INDEX ON combined_repo_metrics_api (classification_label);
CREATE INDEX ON combined_repo_metrics_api (app_id);
CREATE INDEX ON combined_repo_metrics_api (avg_cyclomatic_complexity);
CREATE INDEX ON combined_repo_metrics_api (repo_size_bytes);
CREATE INDEX ON combined_repo_metrics_api (all_languages);
