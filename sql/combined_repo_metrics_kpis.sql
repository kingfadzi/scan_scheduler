DROP MATERIALIZED VIEW IF EXISTS combined_repo_metrics_api CASCADE;

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
    iac_dockerfile, 
    total_token_count, 
    function_count, 
    total_cyclomatic_complexity,
    total_commits,
    avg_cyclomatic_complexity,
    number_of_contributors,
    repo_size_bytes,
    last_commit_date,
    updated_at
FROM combined_repo_metrics
ORDER BY repo_id;

CREATE INDEX IF NOT EXISTS idx_crmapi_host_name
    ON combined_repo_metrics_api(host_name);
CREATE INDEX IF NOT EXISTS idx_crmapi_activity_status
    ON combined_repo_metrics_api(activity_status);
CREATE INDEX IF NOT EXISTS idx_crmapi_tc
    ON combined_repo_metrics_api(tc);
CREATE INDEX IF NOT EXISTS idx_crmapi_main_language
    ON combined_repo_metrics_api(main_language);
CREATE INDEX IF NOT EXISTS idx_crmapi_classification_label
    ON combined_repo_metrics_api(classification_label);
CREATE INDEX IF NOT EXISTS idx_crmapi_app_id
    ON combined_repo_metrics_api(app_id);
CREATE INDEX IF NOT EXISTS idx_crmapi_avg_ccn
    ON combined_repo_metrics_api(avg_cyclomatic_complexity);
CREATE INDEX IF NOT EXISTS idx_crmapi_repo_size_bytes
    ON combined_repo_metrics_api(repo_size_bytes);
CREATE INDEX IF NOT EXISTS idx_crmapi_all_languages
    ON combined_repo_metrics_api(all_languages);

CREATE UNIQUE INDEX IF NOT EXISTS idx_crmapi_unique
    ON combined_repo_metrics_api(repo_id);
