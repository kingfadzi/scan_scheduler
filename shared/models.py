from sqlalchemy import create_engine, Column, Integer, String, Text, Float, DateTime, UniqueConstraint, ARRAY
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
    browse_url = Column(String)
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

#Gitlog data
class RepoMetrics(Base):
    __tablename__ = "repo_metrics"
    repo_id = Column(String, primary_key=True)
    repo_size_bytes = Column(Float, nullable=False)
    code_size_bytes = Column(Float, nullable=False)
    file_count = Column(Integer, nullable=False)
    total_commits = Column(Integer, nullable=False)
    number_of_contributors = Column(Integer, nullable=False)
    activity_status = Column(String)
    last_commit_date = Column(DateTime)
    repo_age_days = Column(Integer, nullable=False)
    active_branch_count = Column(Integer, nullable=False)
    top_contributor_commits = Column(Integer, nullable=True)
    commits_by_top_3_contributors = Column(Integer, nullable=True)
    recent_commit_dates = Column(ARRAY(DateTime), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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

class GrypeResult(Base):
    __tablename__ = "grype_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(String, nullable=False)
    cve = Column(String, nullable=False)  # CVE ID or equivalent
    description = Column(Text)
    severity = Column(String, nullable=False)
    language = Column(String, nullable=False)
    package = Column(String, nullable=False)
    version = Column(String, nullable=False)
    fix_versions = Column(Text)
    fix_state = Column(Text)
    file_path = Column(Text)
    cvss = Column(Text)

class CheckovSummary(Base):
    __tablename__ = "checkov_summary"
    id = Column(Integer, primary_key=True)
    repo_id = Column(String, nullable=False)
    check_type = Column(String, nullable=False)
    #language = Column(String, nullable=False)
    passed = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    skipped = Column(Integer, default=0)
    resource_count = Column(Integer, default=0)
    parsing_errors = Column(Integer, default=0)



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


class CombinedRepoMetrics(Base):
    __tablename__ = "combined_repo_metrics"
    repo_id = Column(String, primary_key=True)
    main_language = Column(String, nullable=False)
    activity_status = Column(String, nullable=False)
    classification_label = Column(String, nullable=True)



class Dependency(Base):
    __tablename__ = 'dependencies'

    id = Column(Integer, primary_key=True)
    repo_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    version = Column(String, nullable=False)
    package_type = Column(String, nullable=False)
    category = Column(String, nullable=True)
    sub_category = Column(String, nullable=True)

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


class BuildTool(Base):
    __tablename__ = 'build_tools'

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(String, nullable=False)
    tool = Column(String, nullable=False)
    tool_version = Column(String, nullable=True)
    runtime_version = Column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            'repo_id', 
            'tool', 
            'tool_version', 
            'runtime_version',
            name='_build_tools_full_uc'
        ),
    )

class SyftDependency(Base):
    __tablename__ = 'syft_dependencies'
    
    id = Column(String, primary_key=True)
    repo_id = Column(String, nullable=False)
    package_name = Column(String, nullable=False)
    version = Column(String)
    package_type = Column(String, nullable=False)
    licenses = Column(Text)
    locations = Column(Text)
    language = Column(String)
    category = Column(String)
    sub_category = Column(String)
    framework = Column(String)

class IacComponent(Base):
    __tablename__ = "iac_components"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(String(255), nullable=False)
    repo_slug = Column(String(255), nullable=False)
    repo_name = Column(String(255), nullable=False)
    file_path = Column(String(1024), nullable=False)
    category = Column(String(255), nullable=False)
    subcategory = Column(String(255), nullable=False)
    framework = Column(String(255), nullable=False)
    scan_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    