from datetime import datetime
import json
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import create_engine, func
from prefect import flow, task
from prefect.task_runners import ConcurrentTaskRunner
from prefect.context import get_run_context
from flows.profiles.runtime_version import extract_runtime_version
from prefect.cache_policies import NO_CACHE
from shared.repo_profile_cache import RepoProfileCache
from shared.models import (
    Repository, RepoMetrics, LizardSummary, ClocMetric, BuildTool,
    GoEnryAnalysis, SyftDependency, GrypeResult, TrivyVulnerability,
    XeolResult, SemgrepResult, CheckovSummary
)


DATABASE_URL = "postgresql://postgres:postgres@192.168.1.188:5432/gitlab-usage"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

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
                build_tool = "python"
            elif package_type == "npm":
                build_tool = "node"
            elif package_type == "go-module":
                build_tool = "go"
            elif package_type == "gem":
                build_tool = "ruby"
    return build_tool or "Unknown"


@task
async def fetch_basic_info(repo_id: str):
    with SessionLocal() as session:
        repository = session.query(Repository).filter_by(repo_id=repo_id).first()
        repo_metrics = session.query(RepoMetrics).filter_by(repo_id=repo_id).first()
        build_tool_metadata = session.query(BuildTool).filter_by(repo_id=repo_id).first()
        lizard_summary = session.query(LizardSummary).filter_by(repo_id=repo_id).first()
        if not repository or not repo_metrics:
            raise ValueError(f"Missing repository or metrics for {repo_id}")
        return repository, repo_metrics, build_tool_metadata, lizard_summary

@task
async def fetch_languages(repo_id: str):
    with SessionLocal() as session:
        return session.query(GoEnryAnalysis).filter_by(repo_id=repo_id).all()

@task
async def fetch_cloc(repo_id: str):
    with SessionLocal() as session:
        return session.query(ClocMetric).filter_by(repo_id=repo_id).all()

@task
async def fetch_dependencies(repo_id: str):
    with SessionLocal() as session:
        return session.query(SyftDependency).filter_by(repo_id=repo_id).all()

@task
async def fetch_security(repo_id: str):
    with SessionLocal() as session:
        grype_results = session.query(GrypeResult).filter_by(repo_id=repo_id).all()
        trivy_results = session.query(TrivyVulnerability).filter_by(repo_id=repo_id).all()
        return grype_results, trivy_results

@task
async def fetch_eol(repo_id: str):
    with SessionLocal() as session:
        return session.query(XeolResult).filter_by(repo_id=repo_id).all()

@task
async def fetch_semgrep(repo_id: str):
    with SessionLocal() as session:
        return session.query(SemgrepResult).filter_by(repo_id=repo_id).all()

@task
async def fetch_modernization_signals(repo_id: str):
    with SessionLocal() as session:
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


@task
async def assemble_basic_info(repository, repo_metrics):
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
        "Top Contributor Commits": repo_metrics.top_contributor_commits or 0,
        "Commits by Top 3 Contributors": repo_metrics.commits_by_top_3_contributors or 0,
        "Recent Commit Dates": [
            d.isoformat() if isinstance(d, datetime) else d
            for d in (repo_metrics.recent_commit_dates or [])
        ]
    }

@task
async def assemble_languages_info(languages):
    language_dict = {lang.language: round(lang.percent_usage, 2) for lang in languages}
    main_language = max(language_dict, key=language_dict.get) if language_dict else None
    return {
        "Language Percentages": language_dict,
        "Main Language": main_language,
        "Other Languages": [k for k in language_dict if k != main_language] if main_language else []
    }

@task
async def assemble_code_quality_info(lizard_summary, cloc_metrics):
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
async def assemble_classification_info(repo_metrics, total_loc):
    return {
        "Classification Label": classify_repo(repo_metrics.repo_size_bytes, total_loc)
    }

@task(cache_policy=NO_CACHE)
async def assemble_dependencies_info(session, repo_id, dependencies):
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
        "Runtime Version": extract_runtime_version(session, repo_id)

    }

@task
async def assemble_security_info(grype_results, trivy_results, dependencies):
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
async def assemble_eol_info(eol_results):
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
async def assemble_semgrep_info(semgrep_findings):
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
async def assemble_modernization_info(modernization_signals):
    return {"Modernization Signals": modernization_signals}

@task
async def merge_profile_sections(*sections):
    profile = {}
    for section in sections:
        profile.update(section)
    return profile

@task
async def cache_profile(repo_id: str, complete_profile: dict):
    with SessionLocal() as session:
        existing = session.query(RepoProfileCache).filter_by(repo_id=repo_id).first()
        if existing:
            existing.profile_json = json.dumps(complete_profile)
        else:
            new_cache = RepoProfileCache(repo_id=repo_id, profile_json=json.dumps(complete_profile))
            session.add(new_cache)
        session.commit()
    print(f"Profile cached for {repo_id}")


@flow(
    name="build_profile_flow",
    persist_result=False,
    retries=0,
    flow_run_name=lambda: get_run_context().parameters["repo_id"]
)
async def build_profile_flow(repo_id: str):

    basic_future = fetch_basic_info.submit(repo_id)
    lang_future = fetch_languages.submit(repo_id)
    cloc_future = fetch_cloc.submit(repo_id)
    deps_future = fetch_dependencies.submit(repo_id)
    security_future = fetch_security.submit(repo_id)
    eol_future = fetch_eol.submit(repo_id)
    semgrep_future = fetch_semgrep.submit(repo_id)
    modern_future = fetch_modernization_signals.submit(repo_id)

    repo_data = basic_future.result()
    languages = lang_future.result()
    cloc_metrics = cloc_future.result()
    dependencies = deps_future.result()
    grype, trivy = security_future.result()
    eol_results = eol_future.result()
    semgrep_findings = semgrep_future.result()
    modernization_signals = modern_future.result()
    
    repository, repo_metrics, build_tool_metadata, lizard_summary = repo_data

    # Process data in parallel
    basic_info = assemble_basic_info.submit(repository, repo_metrics)
    lang_info = assemble_languages_info.submit(languages)
    code_quality = assemble_code_quality_info.submit(lizard_summary, cloc_metrics)
    classification = assemble_classification_info.submit(repo_metrics, code_quality.result()["total_loc"])
    with SessionLocal() as session:
        deps_info = assemble_dependencies_info.submit(session, repository.repo_id, dependencies)
    security_info = assemble_security_info.submit(grype, trivy, dependencies)
    eol_info = assemble_eol_info.submit(eol_results)
    semgrep_info = assemble_semgrep_info.submit(semgrep_findings)
    modern_info = assemble_modernization_info.submit(modernization_signals)

    # Merge sections
    complete_profile = merge_profile_sections.submit(
        basic_info.result(),
        lang_info.result(),
        code_quality.result(),
        classification.result(),
        deps_info.result(),
        security_info.result(),
        eol_info.result(),
        semgrep_info.result(),
        modern_info.result()
    )

    # Final cache operation with explicit wait
    cache_future = cache_profile.submit(repo_id, complete_profile.result())
    cache_future.wait()

if __name__ == "__main__":
    build_profile_flow(repo_id="WebGoat/WebGoat")