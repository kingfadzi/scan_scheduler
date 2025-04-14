from datetime import date, datetime
import pandas as pd
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import create_engine, func
from prefect import flow, task
from prefect.task_runners import ConcurrentTaskRunner
from prefect.context import get_run_context
from shared.models import Session
from flows.profiles.helpers import extract_runtime_version, classify_repo, infer_build_tool, DateSafeJSONEncoder
from prefect.cache_policies import NO_CACHE
from shared.repo_profile_cache import RepoProfileCache
from shared.models import Session, IacComponent
from shared.models import (
    Repository, RepoMetrics, LizardSummary, ClocMetric, BuildTool,
    GoEnryAnalysis, SyftDependency, GrypeResult, TrivyVulnerability,
    XeolResult, SemgrepResult, CheckovSummary
)


@task
async def fetch_basic_info(repo_id: str):
    with Session() as session:
        repository = session.query(Repository).filter_by(repo_id=repo_id).first()
        repo_metrics = session.query(RepoMetrics).filter_by(repo_id=repo_id).first()
        build_tool_metadata = session.query(BuildTool).filter_by(repo_id=repo_id).first()
        lizard_summary = session.query(LizardSummary).filter_by(repo_id=repo_id).first()
        if not repository or not repo_metrics:
            raise ValueError(f"Missing repository or metrics for {repo_id}")
        return repository, repo_metrics, build_tool_metadata, lizard_summary

@task
async def fetch_languages(repo_id: str):
    with Session() as session:
        return session.query(GoEnryAnalysis).filter_by(repo_id=repo_id).all()

@task
async def fetch_cloc(repo_id: str):
    with Session() as session:
        return session.query(ClocMetric).filter_by(repo_id=repo_id).all()

@task
async def fetch_dependencies(repo_id: str):
    with Session() as session:
        return session.query(SyftDependency).filter_by(repo_id=repo_id).all()

@task
async def fetch_security(repo_id: str):
    with Session() as session:
        grype_results = session.query(GrypeResult).filter_by(repo_id=repo_id).all()
        trivy_results = session.query(TrivyVulnerability).filter_by(repo_id=repo_id).all()
        return grype_results, trivy_results

@task
async def fetch_eol(repo_id: str):
    with Session() as session:
        return session.query(XeolResult).filter_by(repo_id=repo_id).all()

@task
async def fetch_semgrep(repo_id: str):
    with Session() as session:
        return session.query(SemgrepResult).filter_by(repo_id=repo_id).all()

@task
async def fetch_modernization_signals(repo_id: str):
    with Session() as session:
   
        dockerfile_present = session.query(IacComponent).filter(
            IacComponent.repo_id == repo_id,
            IacComponent.framework.in_(["Dockerfile", "docker-compose"])
        ).first()
  
        cicd_pipeline_present = session.query(IacComponent).filter(
            IacComponent.repo_id == repo_id,
            IacComponent.category == "Developer Platform and CI/CD"
        ).first()

        iac_config_present = session.query(IacComponent).filter(
            IacComponent.repo_id == repo_id,
            IacComponent.category.in_([
                "Infrastructure Platform",
                "Container Platform"
            ])
        ).first()

        return {
            "Dockerfile": dockerfile_present is not None,
            "CI/CD Pipeline": cicd_pipeline_present is not None,
            "IaC Config": iac_config_present is not None,
        }


@task
async def assemble_basic_info(repository, repo_metrics):
    return {
        "Repo ID": repository.repo_id,
        "Repo Name": repository.repo_name,
        "Status": repository.status or "Unknown",
        "VCS Hostname": repository.host_name,
        "App ID": repository.app_id,
        "Last Updated": repository.updated_on.isoformat(),
        "Clone URL SSH": repository.clone_url_ssh,
        "Browse URL": repository.browse_url,
        "Repo Size (MB)": round(repo_metrics.repo_size_bytes / 1_000_000, 2),
        "Code Size (MB)": round((repo_metrics.code_size_bytes or 0) / 1_000_000, 2),
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
    frameworks = [
        f"{dep.framework.strip()}"
        for dep in dependencies
        if dep.framework and dep.framework.strip()
    ]

    return {
        "Dependencies": [{
            "name": dep.package_name,
            "version": dep.version,
            "package_type": dep.package_type,
            "language": dep.language,
            "locations": dep.locations,
            "licenses": dep.licenses,
            "category": dep.category,
            "sub_category": dep.sub_category,
            "framework": dep.framework
        } for dep in dependencies],
        "Total Dependencies": len(dependencies),
        "Frameworks": sorted(list(set(frameworks))),
        "Build Tool": infer_build_tool(dependencies),
        "Runtime Version": extract_runtime_version(session, repo_id)
    }



@task
async def assemble_security_info(grype_results, trivy_results, dependencies):
    # Combine Grype and Trivy vulnerabilities into one list
    combined = []

    for g in grype_results:
        combined.append({
            "package": g.package,
            "version": g.version,
            "severity": g.severity,
            "fix_version": g.fix_versions,
            "source": "Grype"
        })

    for t in trivy_results:
        if t.pkg_name:
            combined.append({
                "package": t.pkg_name,
                "version": t.installed_version,
                "severity": t.severity,
                "fix_version": t.fixed_version,
                "source": "Trivy"
            })

    # If no vulnerabilities, return early
    if not combined:
        return {
            "Vulnerabilities": [],
            "Critical Vuln Count": 0,
            "Vulnerable Dependencies %": 0.0
        }

    # Create a DataFrame for easier handling
    df = pd.DataFrame(combined)

    # Prefer Grype results if a vulnerability appears in both
    df['source_order'] = df['source'].map({'Grype': 0, 'Trivy': 1})

    # Deduplicate based on package, version, and severity
    df = (
        df.sort_values('source_order')
        .drop_duplicates(subset=["package", "version", "severity"])
        .drop(columns=["source_order"])
    )

    # Final metrics
    vulnerabilities = df.to_dict(orient="records")
    critical_count = (df['severity'] == "Critical").sum()
    vuln_dependency_percent = round((len(df) / max(len(dependencies), 1)) * 100, 2)

    return {
        "Vulnerabilities": vulnerabilities,
        "Critical Vuln Count": critical_count,
        "Vulnerable Dependencies %": vuln_dependency_percent
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



@task(retries=0, retry_delay_seconds=2)
async def cache_profile(repo_id: str, complete_profile: dict):
    from datetime import date
    import json
    
    class DateEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            return super().default(obj)

    try:
        with Session() as session:

            sanitized_profile = json.loads(
                json.dumps(complete_profile, cls=DateSafeJSONEncoder)
            )

            existing = session.query(RepoProfileCache).filter_by(repo_id=repo_id).first()
            if existing:
                existing.profile_json = json.dumps(sanitized_profile)
            else:
                new_cache = RepoProfileCache(
                    repo_id=repo_id,
                    profile_json=json.dumps(sanitized_profile)
                )
                session.add(new_cache)
            session.commit()
        print(f"Profile cached for {repo_id}")
    except Exception as exc:
        print(f"Error caching profile for {repo_id}: {exc}")
        raise exc


@flow(
    name="build_profile_flow",
    persist_result=False,
    retries=0,
    flow_run_name=lambda: get_run_context().parameters["repo_id"]
)
async def build_profile_flow(repo_id: str):
    try:
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

        basic_info = assemble_basic_info.submit(repository, repo_metrics)
        lang_info = assemble_languages_info.submit(languages)
        code_quality = assemble_code_quality_info.submit(lizard_summary, cloc_metrics)
        classification = assemble_classification_info.submit(repo_metrics, code_quality.result()["total_loc"])
        with Session() as session:
            deps_info = assemble_dependencies_info.submit(session, repository.repo_id, dependencies)
        security_info = assemble_security_info.submit(grype, trivy, dependencies)
        eol_info = assemble_eol_info.submit(eol_results)
        semgrep_info = assemble_semgrep_info.submit(semgrep_findings)
        modern_info = assemble_modernization_info.submit(modernization_signals)

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

        cache_profile.submit(repo_id, complete_profile.result()).result()

    except Exception as exc:
        print(f"Flow failed for repo_id {repo_id} with error: {exc}")
        raise exc


if __name__ == "__main__":
    build_profile_flow(repo_id="WebGoat/WebGoat")