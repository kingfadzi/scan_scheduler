CREATE MATERIALIZED VIEW app_component_repo_mapping AS
WITH distinct_business_apps AS (
    SELECT DISTINCT component_id, identifier
    FROM component_mapping
    WHERE mapping_type = 'business_application'
)
SELECT
    (vc.project_key || '/' || vc.repo_slug) AS repo_id,
    vc.component_id,
    vc.component_name,
    string_agg(DISTINCT vc.transaction_cycle, ', ') AS transaction_cycle,
    vc.name AS version_control_name,
    vc.identifier AS version_control_identifier,
    vc.web_url,
    string_agg(DISTINCT dba.identifier, ', ') AS app_identifiers
FROM
    component_mapping vc
        LEFT JOIN distinct_business_apps dba
                  ON vc.component_id = dba.component_id
WHERE
    vc.mapping_type = 'version_control'
  AND COALESCE(vc.project_key, '') <> ''
  AND COALESCE(vc.repo_slug, '') <> ''
GROUP BY
    vc.project_key,
    vc.repo_slug,
    vc.component_id,
    vc.component_name,
    vc.name,
    vc.identifier,
    vc.web_url
HAVING
    COUNT(dba.identifier) > 0;

CREATE INDEX idx_app_component_repo_mapping_repo_id
    ON app_component_repo_mapping (repo_id);

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_app_component_repo_mapping_transaction_cycle_trgm
    ON app_component_repo_mapping USING gin (transaction_cycle gin_trgm_ops);
