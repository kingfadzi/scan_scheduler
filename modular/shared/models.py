from sqlalchemy import create_engine, Column, Integer, String, Text, Float, DateTime, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from config.config import Config

# Construct the database URL using Config
DB_URL = (
    f"postgresql+psycopg2://{Config.METRICS_DATABASE_USER}:"
    f"{Config.METRICS_DATABASE_PASSWORD}@"
    f"{Config.METRICS_DATABASE_HOST}:"
    f"{Config.METRICS_DATABASE_PORT}/"
    f"{Config.METRICS_DATABASE_NAME}"
)

engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)
Base = declarative_base()

class Repository(Base):
    __tablename__ = "bitbucket_repositories"
    repo_id = Column(String, primary_key=True)
    repo_name = Column(String, nullable=False)
    project_key = Column(String, nullable=False)
    repo_slug = Column(String, nullable=False)
    app_id = Column(String)
    host_name = Column(String)
    tc_cluster = Column(String)
    tc = Column(String)
    clone_url_ssh = Column(String)
    status = Column(String)
    comment = Column(String)
    updated_on = Column(DateTime)

class GoEnryAnalysis(Base):
    __tablename__ = "go_enry_analysis"
    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(String, nullable=False)
    language = Column(String, nullable=False)
    percent_usage = Column(Float, nullable=False)
    analysis_date = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('repo_id', 'language', name='_repo_language_uc'),)

class RepoMetrics(Base):
    __tablename__ = "repo_metrics"
    repo_id = Column(String, primary_key=True)
    repo_size_bytes = Column(Float, nullable=False)
    file_count = Column(Integer, nullable=False)
    total_commits = Column(Integer, nullable=False)
    number_of_contributors = Column(Integer, nullable=False)
    activity_status = Column(String)
    last_commit_date = Column(DateTime)
    repo_age_days = Column(Integer, nullable=False)
    active_branch_count = Column(Integer, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Lizard Metrics Model
class LizardMetric(Base):
    __tablename__ = "lizard_metrics"
    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(String, nullable=False)
    file_name = Column(Text)
    function_name = Column(Text)
    long_name = Column(Text)
    nloc = Column(Integer)
    ccn = Column(Integer)
    token_count = Column(Integer)
    param = Column(Integer)
    function_length = Column(Integer)
    start_line = Column(Integer)
    end_line = Column(Integer)
    __table_args__ = (
        UniqueConstraint("repo_id", "file_name", "function_name", name="lizard_metric_uc"),
    )

# Lizard Summary Model
class LizardSummary(Base):
    __tablename__ = "lizard_summary"
    repo_id = Column(String, primary_key=True)
    total_nloc = Column(Integer)
    avg_ccn = Column(Float)
    total_token_count = Column(Integer)
    function_count = Column(Integer)
    total_ccn = Column(Integer)

# Cloc Metrics Model
class ClocMetric(Base):
    __tablename__ = "cloc_metrics"
    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(String, nullable=False)
    language = Column(Text)
    files = Column(Integer)
    blank = Column(Integer)
    comment = Column(Integer)
    code = Column(Integer)
    __table_args__ = (
        UniqueConstraint("repo_id", "language", name="cloc_metric_uc"),
    )

# Checkov Results Model
class CheckovResult(Base):
    __tablename__ = "checkov_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(String, nullable=False)
    resource = Column(Text)
    check_name = Column(Text)
    check_result = Column(Text)
    severity = Column(Text)
    __table_args__ = (
        UniqueConstraint("repo_id", "resource", "check_name", name="checkov_result_uc"),
    )

class CheckovSarifResult(Base):
    __tablename__ = "checkov_sarif_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(String, nullable=False)
    rule_id = Column(Text)
    rule_name = Column(Text)
    severity = Column(Text)
    file_path = Column(Text)
    start_line = Column(Integer)
    end_line = Column(Integer)
    message = Column(Text)

class DependencyCheckResult(Base):
    __tablename__ = "dependency_check_results"
    id = Column(Integer, primary_key=True, autoincrement=True)  # Auto-incrementing primary key
    repo_id = Column(String, nullable=False)  # Repository ID (foreign key or unique reference)
    cve = Column(String, nullable=False)  # Common Vulnerabilities and Exposures ID
    description = Column(Text, nullable=True)  # Detailed description of the vulnerability
    severity = Column(String, nullable=True)  # Severity level (e.g., High, Medium, Low)
    vulnerable_software = Column(String, nullable=True)  # List of vulnerable software versions
    __table_args__ = (
        UniqueConstraint("repo_id", "cve", name="dependency_check_result_uc"),  # Unique constraint on repo_id and cve
    )

class GrypeResult(Base):
    __tablename__ = "grype_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(String, nullable=False)
    cve = Column(String, nullable=False)  # CVE ID or equivalent
    description = Column(Text)
    severity = Column(String, nullable=False)
    language = Column(String, nullable=False)
    package = Column(String, nullable=False)  # Name of the affected package
    version = Column(String, nullable=False)  # Version of the affected package
    fix_versions = Column(Text)
    fix_state = Column(Text)
    file_path = Column(Text)  # File path of the affected artifact
    cvss = Column(Text)  # CVSS scores, serialized as a JSON string
    __table_args__ = (
        UniqueConstraint("repo_id", "cve", "package", "version", name="grype_result_uc"),
    )

class CheckovSummary(Base):
    __tablename__ = "checkov_summary"
    id = Column(Integer, primary_key=True)
    repo_id = Column(String, nullable=False)
    check_type = Column(String, nullable=False)
    language = Column(String, nullable=False)
    passed = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    skipped = Column(Integer, default=0)
    resource_count = Column(Integer, default=0)
    parsing_errors = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("repo_id", "check_type", name="uq_repo_check"),
    )

class CheckovFiles(Base):
    __tablename__ = "checkov_files"
    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(String, nullable=False)
    check_type = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_abs_path = Column(String, nullable=True)
    resource_count = Column(Integer, nullable=False, default=0)
    __table_args__ = (
        UniqueConstraint("repo_id", "check_type", "file_path", name="uq_repo_check_file"),
    )

class CheckovChecks(Base):
    __tablename__ = "checkov_checks"
    id = Column(Integer, primary_key=True)
    repo_id = Column(String, nullable=False)
    file_path = Column(Text, nullable=False)
    check_type = Column(String, nullable=False)
    check_id = Column(String, nullable=False)
    check_name = Column(String)
    result = Column(String)
    severity = Column(String)
    resource = Column(Text)
    guideline = Column(Text)
    start_line = Column(Integer)
    end_line = Column(Integer)

    __table_args__ = (
        UniqueConstraint("repo_id", "file_path", "check_type", "check_id", name="uq_repo_check_id"),
    )

class TrivyVulnerability(Base):
    __tablename__ = "trivy_vulnerability"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(String, nullable=False)
    target = Column(String, nullable=False)
    resource_class = Column(String, nullable=True)  # Class of resource (e.g., config, lang-pkgs)
    resource_type = Column(String, nullable=True)  # Type of resource (e.g., dockerfile, terraform)
    vulnerability_id = Column(String, nullable=False)
    pkg_name = Column(String, nullable=True)
    installed_version = Column(String, nullable=True)
    fixed_version = Column(String, nullable=True)
    severity = Column(String, nullable=False)
    primary_url = Column(String, nullable=True)
    description = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint('repo_id', 'vulnerability_id', 'pkg_name', name='uq_repo_vuln_pkg'),
    )

class AnalysisExecutionLog(Base):
    __tablename__ = "analysis_execution_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    method_name = Column(String, nullable=False)
    stage = Column(String, nullable=True)
    run_id = Column(String, nullable=True)
    repo_id = Column(String, nullable=True)  # Added repo_id
    status = Column(String, nullable=False)  # "SUCCESS" or "FAILURE"
    message = Column(String, nullable=True)  # Success message or error details
    execution_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    duration = Column(Float, nullable=False)


class SemgrepResult(Base):
    __tablename__ = "semgrep_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(String, nullable=False)
    path = Column(String, nullable=False)
    start_line = Column(Integer, nullable=False)
    end_line = Column(Integer, nullable=False)
    rule_id = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    category = Column(String, nullable=True)
    subcategory = Column(Text, nullable=True)  # Added field for subcategory
    technology = Column(String, nullable=True)
    cwe = Column(Text, nullable=True)
    likelihood = Column(String, nullable=True)  # Added field for likelihood
    impact = Column(String, nullable=True)  # Added field for impact
    confidence = Column(String, nullable=True)  # Added field for confidence

    __table_args__ = (
        UniqueConstraint("repo_id", "path", "start_line", "rule_id", name="uq_semgrep_results"),
    )

class ComponentMapping(Base):
    __tablename__ = "component_mapping"
    id = Column(Integer, primary_key=True, autoincrement=True)
    component_id = Column(Integer)
    component_name = Column(String)
    tc = Column(String)
    mapping_type = Column(String)
    instance_url = Column(String)
    tool_type = Column(String)
    name = Column(String)
    identifier = Column(String)
    web_url = Column(String)
    project_key = Column(String)
    repo_slug = Column(String)

class Ruleset(Base):
    __tablename__ = 'kantra_rulesets'
    name = Column(String, primary_key=True)
    description = Column(Text, nullable=True)

class Violation(Base):
    __tablename__ = "kantra_violations"
    id = Column(Integer, primary_key=True)
    repo_id = Column(String)
    ruleset_name = Column(String)
    rule_name = Column(String)
    description = Column(String)
    category = Column(String)
    effort = Column(Integer)
    __table_args__ = (
        UniqueConstraint("repo_id", "ruleset_name", "rule_name", "description", name="uq_repo_rule_desc"),
    )

class Label(Base):
    __tablename__ = 'kantra_labels'
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String, nullable=False)
    value = Column(String, nullable=False)
    __table_args__ = (
        UniqueConstraint("key", "value", name="unique_key_value_pair"),
    )

class CombinedRepoMetrics(Base):
    __tablename__ = "combined_repo_metrics"
    repo_id = Column(String, primary_key=True)
    main_language = Column(String, nullable=False)
    activity_status = Column(String, nullable=False)
    classification_label = Column(String, nullable=True)

class ViolationLabel(Base):
    __tablename__ = "kantra_violation_labels"
    violation_id = Column(Integer, primary_key=True)
    label_id = Column(Integer, primary_key=True)


class Dependency(Base):
    __tablename__ = 'dependencies'

    id = Column(Integer, primary_key=True)
    repo_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    version = Column(String, nullable=False)
    package_type = Column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint('repo_id', 'name', 'version', name='uq_repo_name_version'),
    )

class XeolResult(Base):
    __tablename__ = 'xeol_results'

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(String, nullable=False)
    product_name = Column(String, nullable=True)
    product_permalink = Column(String, nullable=True)
    release_cycle = Column(String, nullable=True)
    eol_date = Column(String, nullable=True)
    latest_release = Column(String, nullable=True)
    latest_release_date = Column(String, nullable=True)
    release_date = Column(String, nullable=True)
    artifact_name = Column(String, nullable=True)
    artifact_version = Column(String, nullable=True)
    artifact_type = Column(String, nullable=True)
    file_path = Column(String, nullable=True)
    language = Column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint('repo_id', 'artifact_name', 'artifact_version', name='_xeol_result_uc'),
    )

