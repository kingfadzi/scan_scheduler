CREATE EXTENSION IF NOT EXISTS pg_trgm;

DROP MATERIALIZED VIEW IF EXISTS app_component_repo_mapping CASCADE;

CREATE MATERIALIZED VIEW app_component_repo_mapping AS
WITH distinct_business_apps AS (
    SELECT DISTINCT component_id, identifier
    FROM component_mapping
    WHERE mapping_type = 'it_business_application'
)
SELECT
    -- Remove the first segment (org/) from repo_slug, keeping only sub/subN/repo
    REGEXP_REPLACE(vc.repo_slug, '^[^/]+/', '', '') AS repo_id,

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
    vc.repo_slug,
    vc.component_id,
    vc.component_name,
    vc.name,
    vc.identifier,
    vc.web_url
HAVING
    COUNT(dba.identifier) > 0;

CREATE UNIQUE INDEX idx_app_component_repo_mapping_repo_id
    ON app_component_repo_mapping (repo_id);

REFRESH MATERIALIZED VIEW CONCURRENTLY app_component_repo_mapping;
