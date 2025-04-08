import json
from sqlalchemy.orm import Session
from shared.repo_profile_cache import RepoProfileCache
from shared.models import (
    Repository, RepoMetrics, LizardSummary, ClocMetric, BuildTool,
    GoEnryAnalysis, SyftDependency, GrypeResult, TrivyVulnerability,
    XeolResult, SemgrepResult, CheckovSummary
)
import datetime
from sqlalchemy import func

def classify_repo(repo_size_bytes: float, total_loc: int) -> str:
    if repo_size_bytes is None:
        repo_size_bytes = 0
    if total_loc is None:
        total_loc = 0

    if total_loc < 100:
        if repo_size_bytes < 1_000_000:
            return "Empty/Minimal"
        else:
            return "Docs/Data"
    else:
        if repo_size_bytes < 1_000_000:
            return "Tiny"
        elif repo_size_bytes < 10_000_000:
            return "Small"
        elif repo_size_bytes < 100_000_000:
            return "Medium"
        elif repo_size_bytes < 1_000_000_000:
            return "Large"
        else:
            return "Massive"

def infer_build_tool(syft_deps):
    build_tool = None
    for dep in syft_deps:
        name = (dep.package_name or "").lower()
        ptype = (dep.package_type or "").lower()
        version = (dep.version or "").strip()
        locations = (dep.locations or "").lower()

        if "gradle-wrapper" in name:
            build_tool = f"gradle-wrapper:{version}" if version else "gradle-wrapper"
            break
        elif "maven-wrapper" in name:
            build_tool = f"maven-wrapper:{version}" if version else "maven-wrapper"
            break

        if ptype == "java-archive" and "pom.xml" in locations:
            build_tool = "maven"

        if not build_tool:
            if ptype == "python":
                build_tool = "python"
            elif ptype == "npm":
                build_tool = "node"
            elif ptype == "go-module":
                build_tool = "go"
            elif ptype == "gem":
                build_tool = "ruby"

    return build_tool or "Unknown"

def build_profile(session: Session, repo_id: str) -> dict:
    profile = {}

    repo = session.query(Repository).filter_by(repo_id=repo_id).first()
    metrics = session.query(RepoMetrics).filter_by(repo_id=repo_id).first()
    lizard = session.query(LizardSummary).filter_by(repo_id=repo_id).first()
    buildtool = session.query(BuildTool).filter_by(repo_id=repo_id).first()

    if not repo or not metrics:
        return None

    profile["Repo ID"] = repo.repo_id
    profile["Repo Name"] = repo.repo_name
    profile["Status"] = repo.status or "Unknown"
    profile["VCS Hostname"] = repo.host_name
    profile["Last Updated"] = repo.updated_on.isoformat()
    profile["Clone URL SSH"] = repo.clone_url_ssh

    repo_size_mb = round(metrics.repo_size_bytes / 1_000_000, 2)
    profile["Repo Size (MB)"] = repo_size_mb
    profile["File Count"] = metrics.file_count
    profile["Total Commits"] = metrics.total_commits
    profile["Contributors"] = metrics.number_of_contributors
    profile["Activity Status"] = metrics.activity_status or "Unknown"
    profile["Last Commit Date"] = metrics.last_commit_date.isoformat() if metrics.last_commit_date else None
    profile["Repo Age (Years)"] = round(metrics.repo_age_days / 365, 2)
    profile["Active Branch Count"] = metrics.active_branch_count
    profile["Recent Commit Dates"] = [
        dt.isoformat() if hasattr(dt, "isoformat") else dt
        for dt in (metrics.recent_commit_dates or [])
    ]

    if metrics.total_commits and metrics.top_contributor_commits is not None:
        profile["Single Developer %"] = round((metrics.top_contributor_commits / metrics.total_commits) * 100, 2)
    else:
        profile["Single Developer %"] = None


    dockerfile_present = session.query(GoEnryAnalysis).filter(
        func.lower(GoEnryAnalysis.language) == "dockerfile"
    ).filter_by(repo_id=repo_id).first()
    profile["Dockerfile"] = dockerfile_present is not None

    iac_check = session.query(CheckovSummary).filter(
        CheckovSummary.repo_id == repo_id,
        CheckovSummary.check_type.in_([
            "cloudformation", "terraform", "terraform_plan", "kubernetes", "helm", "kustomize"
        ])
    ).first()
    profile["IaC Config Present"] = iac_check is not None

    cicd_check = session.query(CheckovSummary).filter(
        CheckovSummary.repo_id == repo_id,
        CheckovSummary.check_type.in_(["gitlab_ci", "bitbucket_pipelines"])
    ).first()
    profile["CI/CD Present"] = cicd_check is not None

    secrets_check = session.query(CheckovSummary).filter(
        CheckovSummary.repo_id == repo_id,
        CheckovSummary.check_type == "secrets"
    ).first()
    profile["Hardcoded Secrets Found"] = secrets_check.failed if secrets_check else 0

    langs = session.query(GoEnryAnalysis).filter_by(repo_id=repo_id).all()
    if langs:
        lang_dict = {lang.language: round(lang.percent_usage, 2) for lang in langs}
        profile["Language Percentages"] = lang_dict
        if lang_dict:
            main_lang = max(lang_dict, key=lang_dict.get)
            profile["Main Language"] = main_lang
            profile["Other Languages"] = [k for k in lang_dict if k != main_lang]
        else:
            profile["Main Language"] = None
            profile["Other Languages"] = []
    else:
        profile["Language Percentages"] = {}
        profile["Main Language"] = None
        profile["Other Languages"] = []

    if lizard:
        profile["Total NLOC"] = lizard.total_nloc
        profile["Avg Cyclomatic Complexity"] = round(lizard.avg_ccn or 0, 2)
        profile["Total Tokens"] = lizard.total_token_count
        profile["Total Functions"] = lizard.function_count
        profile["Total Cyclomatic Complexity"] = lizard.total_ccn
    else:
        profile["Total NLOC"] = profile["Avg Cyclomatic Complexity"] = 0
        profile["Total Tokens"] = profile["Total Functions"] = profile["Total Cyclomatic Complexity"] = 0

    cloc = session.query(ClocMetric).filter_by(repo_id=repo_id).all()
    if cloc:
        total_loc = sum(x.code for x in cloc)
        profile["Lines of Code"] = total_loc
        profile["Blank Lines"] = sum(x.blank for x in cloc)
        profile["Comment Lines"] = sum(x.comment for x in cloc)
    else:
        total_loc = 0
        profile["Lines of Code"] = profile["Blank Lines"] = profile["Comment Lines"] = 0

    classification = classify_repo(metrics.repo_size_bytes, total_loc)
    profile["Classification Label"] = classification

    deps = session.query(SyftDependency).filter_by(repo_id=repo_id).all()
    seen_deps = set()
    profile["Dependencies"] = []
    for d in deps:
        key = (d.package_name, d.version)
        if key not in seen_deps:
            seen_deps.add(key)
            profile["Dependencies"].append({
                "name": d.package_name,
                "version": d.version,
                "package_type": d.package_type,
                "language": d.language,
                "locations": d.locations,
                "licenses": d.licenses,
            })
    profile["Total Dependencies"] = len(profile["Dependencies"])

    profile["Build Tool"] = infer_build_tool(deps)
    profile["Runtime Version"] = buildtool.runtime_version if buildtool else None

    grype_vulns = session.query(GrypeResult).filter_by(repo_id=repo_id).all()
    trivy_vulns = session.query(TrivyVulnerability).filter_by(repo_id=repo_id).all()
    seen_vulns = set()
    merged_vulns = []
    for v in grype_vulns:
        key = (v.package, v.version)
        if key not in seen_vulns:
            seen_vulns.add(key)
            merged_vulns.append({
                "package": v.package,
                "version": v.version,
                "severity": v.severity,
                "fix_version": v.fix_versions,
                "source": "G"
            })
    for v in trivy_vulns:
        if v.pkg_name:
            key = (v.pkg_name, v.installed_version)
            if key not in seen_vulns:
                seen_vulns.add(key)
                merged_vulns.append({
                    "package": v.pkg_name,
                    "version": v.installed_version,
                    "severity": v.severity,
                    "fix_version": v.fixed_version,
                    "source": "T"
                })

    profile["Vulnerabilities"] = merged_vulns
    profile["Critical Vuln Count"] = sum(1 for v in merged_vulns if v["severity"] == "Critical")
    profile["Vulnerable Dependencies %"] = round((len(merged_vulns) / (len(profile["Dependencies"]) or 1)) * 100, 2)

    xeol = session.query(XeolResult).filter_by(repo_id=repo_id).all()
    profile["EOL Results"] = []
    for x in xeol:
        profile["EOL Results"].append({
            "artifact_name": x.artifact_name,
            "artifact_version": x.artifact_version,
            "eol_date": x.eol_date,
            "latest_release": x.latest_release,
        })
    profile["EOL Packages Found"] = len(profile["EOL Results"])

    semgrep = session.query(SemgrepResult).filter_by(repo_id=repo_id).all()
    profile["Semgrep Findings"] = []
    for s in semgrep:
        profile["Semgrep Findings"].append({
            "path": s.path,
            "rule_id": s.rule_id,
            "severity": s.severity,
            "category": s.category,
            "subcategory": s.subcategory,
            "likelihood": s.likelihood,
            "impact": s.impact,
            "confidence": s.confidence,
        })

    return profile
