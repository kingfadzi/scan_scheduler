import json
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import create_engine, func
from prefect import flow, task, concurrent
from prefect.task_runners import ConcurrentTaskRunner

from shared.repo_profile_cache import RepoProfileCache
from shared.models import (
    Repository, RepoMetrics, LizardSummary, ClocMetric, BuildTool,
    GoEnryAnalysis, SyftDependency, GrypeResult, TrivyVulnerability,
    XeolResult, SemgrepResult, CheckovSummary
)

# =========================
# Database Setup
# =========================

DATABASE_URL = "postgresql://postgres:postgres@192.168.1.188:5432/gitlab-usage"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# =========================
# Helper Functions
# =========================

def classify_repo(repo_size_bytes: float, total_loc: int) -> str:
    if repo_size_bytes is None:
        repo_size_bytes = 0
    if total_loc is None:
        total_loc = 0
    if total_loc < 100:
        return "Empty/Minimal" if repo_size_bytes < 1_000_000 else "Docs/Data"
    if repo_size_bytes < 1_000_000:
        return "Tiny"
    if repo_size_bytes < 10_000_000:
        return "Small"
    if repo_size_bytes < 100_000_000:
        return "Medium"
    if repo_size_bytes < 1_000_000_000:
        return "Large"
    return "Massive"

def infer_build_tool(syft_dependencies):
    build_tool = None
    for dependency in syft_dependencies:
        name = (dependency.package_name or "").lower()
        package_type = (dependency.package_type or "").lower()
        version = (dependency.version or "").strip()
        locations = (dependency.locations or "").lower()

        if "gradle-wrapper" in name:
            build_tool = f"gradle-wrapper:{version}" if version else "gradle-wrapper"
            break
        if "maven-wrapper" in name:
            build_tool = f"maven-wrapper:{version}" if version else "maven-wrapper"
            break
        if package_type == "java-archive" and "pom.xml" in locations:
            build_tool = "maven"
        if not build_tool:
            if package_type == "python":
                build_tool = f"python:{version}" if version else "python"
            elif package_type == "npm":
                build_tool = f"node:{version}" if version else "node"
            elif package_type == "go-module":
                build_tool = f"go:{version}" if version else "go"
            elif package_type == "gem":
                build_tool = f"ruby:{version}" if version else "ruby"
    return build_tool or "Unknown"

# =========================
# Fetch Tasks
# =========================

@task
def fetch_basic_info(session: Session, repo_id: str):
    repository = session.query(Repository).filter_by(repo_id=repo_id).first()
    repo_metrics = session.query(RepoMetrics).filter_by(repo_id=repo_id).first()
    build_tool_metadata = session.query(BuildTool).filter_by(repo_id=repo_id).first()
    lizard_summary = session.query(LizardSummary).filter_by(repo_id=repo_id).first()
    if not repository or not repo_metrics:
        raise ValueError(f"Missing repository or metrics for {repo_id}")
    return repository, repo_metrics, build_tool_metadata, lizard_summary

@task
def fetch_languages(session: Session, repo_id: str):
    return session.query(GoEnryAnalysis).filter_by(repo_id=repo_id).all()

@task
def fetch_cloc(session: Session, repo_id: str):
    return session.query(ClocMetric).filter_by(repo_id=repo_id).all()

@task
def fetch_dependencies(session: Session, repo_id: str):
    return session.query(SyftDependency).filter_by(repo_id=repo_id).all()

@task
def fetch_security(session: Session, repo_id: str):
    grype_results = session.query(GrypeResult).filter_by(repo_id=repo_id).all()
    trivy_results = session.query(TrivyVulnerability).filter_by(repo_id=repo_id).all()
    return grype_results, trivy_results

@task
def fetch_eol(session: Session, repo_id: str):
    return session.query(XeolResult).filter_by(repo_id=repo_id).all()

@task
def fetch_semgrep(session: Session, repo_id: str):
    return session.query(SemgrepResult).filter_by(repo_id=repo_id).all()

@task
def fetch_modernization_signals(session: Session, repo_id: str):
    dockerfile_present = session.query(GoEnryAnalysis).filter(
        func.lower(GoEnryAnalysis.language) == "dockerfile"
    ).filter_by(repo_id=repo_id).first()

    iac_check = session.query(CheckovSummary).filter(
        CheckovSummary.repo_id == repo_id,
        CheckovSummary.check_type.in_([
            "cloudformation", "terraform", "terraform_plan", "kubernetes", "helm", "kustomize"
        ])
    ).first()

    cicd_check = session.query(CheckovSummary).filter(
        CheckovSummary.repo_id == repo_id,
        CheckovSummary.check_type.in_(["gitlab_ci", "bitbucket_pipelines"])
    ).first()

    secrets_check = session.query(CheckovSummary).filter(
        CheckovSummary.repo_id == repo_id,
        CheckovSummary.check_type == "secrets"
    ).first()

    return {
        "Dockerfile": dockerfile_present is not None,
        "IaC Config Present": iac_check is not None,
        "CI/CD Present": cicd_check is not None,
        "Hardcoded Secrets Found": secrets_check.failed if secrets_check else 0,
    }

# =========================
# Assemble Section Tasks
# =========================

@task
def assemble_basic_info(repository, repo_metrics):
    return {
        "Repo ID": repository.repo_id,
        "Repo Name": repository.repo_name,
        "Status": repository.status or "Unknown",
        "VCS Hostname": repository.host_name,
        "Last Updated": repository.updated_on.isoformat(),
        "Clone URL SSH": repository.clone_url_ssh,
        "Repo Size (MB)": round(repo_metrics.repo_size_bytes / 1_000_000, 2),
        "File Count": repo_metrics.file_count,
        "Total Commits": repo_metrics.total_commits,
        "Contributors": repo_metrics.number_of_contributors,
        "Activity Status": repo_metrics.activity_status or "Unknown",
        "Last Commit Date": repo_metrics.last_commit_date.isoformat() if repo_metrics.last_commit_date else None,
        "Repo Age (Years)": round(repo_metrics.repo_age_days / 365, 2),
        "Active Branch Count": repo_metrics.active_branch_count,
    }

@task
def assemble_languages_info(languages):
    language_dict = {lang.language: round(lang.percent_usage, 2) for lang in languages}
    main_language = max(language_dict, key=language_dict.get) if language_dict else None
    return {
        "Language Percentages": language_dict,
        "Main Language": main_language,
        "Other Languages": [k for k in language_dict if k != main_language] if main_language else []
    }

@task
def assemble_code_quality_info(lizard_summary, cloc_metrics):
    if lizard_summary:
        lizard_data = {
            "Total NLOC": lizard_summary.total_nloc,
            "Avg Cyclomatic Complexity": round(lizard_summary.avg_ccn or 0, 2),
            "Total Tokens": lizard_summary.total_token_count,
            "Total Functions": lizard_summary.function_count,
            "Total Cyclomatic Complexity": lizard_summary.total_ccn,
        }
    else:
        lizard_data = {k: 0 for k in ["Total NLOC", "Avg Cyclomatic Complexity", "Total Tokens", "Total Functions", "Total Cyclomatic Complexity"]}

    if cloc_metrics:
        total_loc = sum(x.code for x in cloc_metrics)
        cloc_data = {
            "Lines of Code": total_loc,
            "Blank Lines": sum(x.blank for x in cloc_metrics),
            "Comment Lines": sum(x.comment for x in cloc_metrics),
        }
    else:
        total_loc = 0
        cloc_data = {k: 0 for k in ["Lines of Code", "Blank Lines", "Comment Lines"]}

    return {**lizard_data, **cloc_data, "total_loc": total_loc}

@task
def assemble_classification_info(repo_metrics, total_loc):
    return {
        "Classification Label": classify_repo(repo_metrics.repo_size_bytes, total_loc)
    }

@task
def assemble_dependencies_info(dependencies, build_tool_metadata):
    return {
        "Dependencies": [{
            "name": dep.package_name,
            "version": dep.version,
            "package_type": dep.package_type,
            "language": dep.language,
            "locations": dep.locations,
            "licenses": dep.licenses
        } for dep in dependencies],
        "Total Dependencies": len(dependencies),
        "Build Tool": infer_build_tool(dependencies),
        "Runtime Version": build_tool_metadata.runtime_version if build_tool_metadata else None
    }

@task
def assemble_security_info(grype_results, trivy_results, dependencies):
    vulnerabilities = [
        {"package": g.package, "version": g.version, "severity": g.severity, "fix_version": g.fix_versions, "source": "G"}
        for g in grype_results
    ] + [
        {"package": t.pkg_name, "version": t.installed_version, "severity": t.severity, "fix_version": t.fixed_version, "source": "T"}
        for t in trivy_results if t.pkg_name
    ]
    return {
        "Vulnerabilities": vulnerabilities,
        "Critical Vuln Count": sum(1 for v in vulnerabilities if v["severity"] == "Critical"),
        "Vulnerable Dependencies %": round((len(vulnerabilities) / (len(dependencies) or 1)) * 100, 2)
    }

@task
def assemble_eol_info(eol_results):
    return {
        "EOL Results": [{
            "artifact_name": result.artifact_name,
            "artifact_version": result.artifact_version,
            "eol_date": result.eol_date,
            "latest_release": result.latest_release,
        } for result in eol_results],
        "EOL Packages Found": len(eol_results)
    }

@task
def assemble_semgrep_info(semgrep_findings):
    return {
        "Semgrep Findings": [{
            "path": finding.path,
            "rule_id": finding.rule_id,
            "severity": finding.severity,
            "category": finding.category,
            "subcategory": finding.subcategory,
            "likelihood": finding.likelihood,
            "impact": finding.impact,
            "confidence": finding.confidence,
        } for finding in semgrep_findings]
    }

@task
def merge_profile_sections(*sections):
    profile = {}
    for section in sections:
        profile.update(section)
    return profile

@task
def cache_profile(session: Session, repo_id: str, complete_profile: dict):
    existing = session.query(RepoProfileCache).filter_by(repo_id=repo_id).first()
    if existing:
        existing.profile_json = json.dumps(complete_profile)
    else:
        new_cache = RepoProfileCache(repo_id=repo_id, profile_json=json.dumps(complete_profile))
        session.add(new_cache)
    session.commit()
    print(f"Profile cached for {repo_id}")

# =========================
# Main Single-Repo Flow
# =========================

@flow(task_runner=ConcurrentTaskRunner())
def build_profile_flow(repo_id: str):
    session = SessionLocal()
    try:
        # Fetch basic repo metadata
        repository, repo_metrics, build_tool_metadata, lizard_summary = fetch_basic_info(session, repo_id)

        # Fetch all other repo data in parallel
        with concurrent():
            languages_future = fetch_languages.submit(session, repo_id)
            cloc_future = fetch_cloc.submit(session, repo_id)
            dependencies_future = fetch_dependencies.submit(session, repo_id)
            security_future = fetch_security.submit(session, repo_id)
            eol_future = fetch_eol.submit(session, repo_id)
            semgrep_future = fetch_semgrep.submit(session, repo_id)
            modernization_signals_future = fetch_modernization_signals.submit(session, repo_id)

        # Resolve all futures
        languages = languages_future.result()
        cloc_metrics = cloc_future.result()
        dependencies = dependencies_future.result()
        grype_results, trivy_results = security_future.result()
        eol_results = eol_future.result()
        semgrep_findings = semgrep_future.result()
        modernization_signals = modernization_signals_future.result()

        # Assemble sections in parallel
        with concurrent():
            basic_info_future = assemble_basic_info.submit(repository, repo_metrics)
            languages_info_future = assemble_languages_info.submit(languages)
            code_quality_info_future = assemble_code_quality_info.submit(lizard_summary, cloc_metrics)
            dependencies_info_future = assemble_dependencies_info.submit(dependencies, build_tool_metadata)
            security_info_future = assemble_security_info.submit(grype_results, trivy_results, dependencies)
            eol_info_future = assemble_eol_info.submit(eol_results)
            semgrep_info_future = assemble_semgrep_info.submit(semgrep_findings)
            modernization_info_future = assemble_modernization_info.submit(modernization_signals)

        # Resolve assembled sections
        basic_info = basic_info_future.result()
        languages_info = languages_info_future.result()
        code_quality_info = code_quality_info_future.result()
        dependencies_info = dependencies_info_future.result()
        security_info = security_info_future.result()
        eol_info = eol_info_future.result()
        semgrep_info = semgrep_info_future.result()
        modernization_info = modernization_info_future.result()

        classification_info = assemble_classification_info(repo_metrics, code_quality_info["total_loc"])

        complete_profile = merge_profile_sections(
            basic_info,
            languages_info,
            code_quality_info,
            classification_info,
            dependencies_info,
            security_info,
            eol_info,
            semgrep_info,
            modernization_info
        )

        cache_profile(session, repo_id, complete_profile)

    finally:
        session.close()

if __name__ == "__main__":
    build_profile_flow(repo_id="WebGoat/WebGoat")