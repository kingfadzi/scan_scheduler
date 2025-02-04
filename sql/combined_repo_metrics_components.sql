CREATE INDEX IF NOT EXISTS idx_kantra_violations_repo_id ON kantra_violations(repo_id);
CREATE INDEX IF NOT EXISTS idx_kantra_violation_labels_violation_id ON kantra_violation_labels(violation_id);

DROP MATERIALIZED VIEW IF EXISTS combined_repo_violations CASCADE;

CREATE MATERIALIZED VIEW combined_repo_violations AS
SELECT
    crm.repo_id,
    crm.host_name,
    crm.project_key,
    crm.repo_slug,
    crm.classification_label,
    crm.activity_status,
    crm.app_id,
    crm.tc,
    crm.all_languages,
    crm.main_language,
    v.id AS violation_id,
    v.ruleset_name,
    v.rule_name,
    v.description,
    v.category,
    v.effort,
    l.key AS label_key,
    l.value AS label_value
FROM combined_repo_metrics crm
         LEFT JOIN kantra_violations v ON crm.repo_id = v.repo_id
         LEFT JOIN kantra_violation_labels vl ON v.id = vl.violation_id
         LEFT JOIN kantra_labels l ON vl.label_id = l.id
ORDER BY crm.repo_id, v.id;

CREATE INDEX IF NOT EXISTS idx_combined_repo_violations_label_key ON combined_repo_violations(label_key);
CREATE INDEX IF NOT EXISTS idx_combined_repo_violations_label_composite ON combined_repo_violations(label_key, label_value, repo_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_combined_repo_violations_unique ON combined_repo_violations(repo_id, violation_id, label_key, label_value);

REFRESH MATERIALIZED VIEW CONCURRENTLY combined_repo_violations;
