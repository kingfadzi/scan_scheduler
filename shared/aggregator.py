import json
from sqlalchemy.orm import Session
from shared.repo_profile_cache import RepoProfileCache
from shared.models import (
    Repository, RepoMetrics, LizardSummary, ClocMetric, BuildTool,
    GoEnryAnalysis, SyftDependency, GrypeResult, TrivyVulnerability,
    XeolResult, SemgrepResult, CheckovSummary
)
import datetime

def classify_repo(repo_size_bytes: float, total_loc: int) -> str:

    if repo_size_bytes is None:
        repo_size_bytes = 0
    if total_loc is None:
        total_loc = 0

    if total_loc < 100:
        # "Empty/Minimal" or "Docs/Data"
        if repo_size_bytes < 1_000_000:
            return "Empty/Minimal"
        else:
            return "Docs/Data"
    else:
        # Enough code
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
            build_tool = f"gradle:{version}" if version else "gradle"
            break
        elif "maven-wrapper" in name:
            build_tool = f"maven:{version}" if version else "maven"
            break

        if ptype == "java-archive" and "pom.xml" in locations:
            build_tool = "maven"

        if not build_tool:
            if ptype == "python":
                build_tool = f"python:{version}" if version else "python"
            elif ptype == "npm":
                build_tool = f"node:{version}" if version else "node"
            elif ptype == "go-module":
                build_tool = f"go:{version}" if version else "go"
            elif ptype == "gem":
                build_tool = f"ruby:{version}" if version else "ruby"

    return build_tool or "Unknown"


def build_profile(session: Session, repo_id: str) -> dict:
    profile = {}

    # --------------- BASIC INFO -------------------
    repo = session.query(Repository).filter_by(repo_id=repo_id).first()
    metrics = session.query(RepoMetrics).filter_by(repo_id=repo_id).first()
    lizard = session.query(LizardSummary).filter_by(repo_id=repo_id).first()
    buildtool = session.query(BuildTool).filter_by(repo_id=repo_id).first()

    if not repo or not metrics:
        return None  # Can't build profile without basics

    profile["Repo ID"] = repo.repo_id
    profile["Repo Name"] = repo.repo_name
    profile["Status"] = repo.status or "Unknown"
    profile["VCS Hostname"] = repo.host_name
    profile["Last Updated"] = repo.updated_on.isoformat()
    profile["Clone URL SSH"] = repo.clone_url_ssh

    # Convert bytes -> MB for display
    repo_size_mb = round(metrics.repo_size_bytes / 1_000_000, 2)
    profile["Repo Size (MB)"] = repo_size_mb
    profile["File Count"] = metrics.file_count
    profile["Total Commits"] = metrics.total_commits
    profile["Contributors"] = metrics.number_of_contributors
    profile["Activity Status"] = metrics.activity_status or "Unknown"
    profile["Last Commit Date"] = metrics.last_commit_date.isoformat() if metrics.last_commit_date else None
    profile["Repo Age (Years)"] = round(metrics.repo_age_days / 365, 2)
    profile["Active Branch Count"] = metrics.active_branch_count

    # --------------- MODERNIZATION SIGNALS -------------------
    dockerfile_present = session.query(GoEnryAnalysis).filter(
        GoEnryAnalysis.repo_id == repo_id,
        GoEnryAnalysis.language.ilike("Dockerfile")
    ).first()
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


    # --------------- LANGUAGES -------------------
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

    # --------------- CLOC + LIZARD -------------------
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

    # --------------- CLASSIFICATION LABEL -------------------
    classification = classify_repo(metrics.repo_size_bytes, total_loc)
    profile["Classification Label"] = classification

    # --------------- DEPENDENCIES -------------------
    deps = session.query(SyftDependency).filter_by(repo_id=repo_id).all()
    profile["Dependencies"] = []
    for d in deps:
        profile["Dependencies"].append({
            "name": d.package_name,
            "version": d.version,
            "package_type": d.package_type,
            "language": d.language,
            "locations": d.locations, 
            "licenses": d.licenses,
        })
    profile["Total Dependencies"] = len(profile["Dependencies"])

    # --------------- BUILD TOOL -------------------
    profile["Build Tool"] = infer_build_tool(deps)
    profile["Runtime Version"] = buildtool.runtime_version if buildtool else None

    # --------------- SECURITY (GRYPE/TRIVY) -------------------
    grype_vulns = session.query(GrypeResult).filter_by(repo_id=repo_id).all()
    trivy_vulns = session.query(TrivyVulnerability).filter_by(repo_id=repo_id).all()

    merged_vulns = []
    for g in grype_vulns:
        merged_vulns.append({
            "package": g.package,
            "version": g.version,
            "severity": g.severity,
            "fix_version": g.fix_versions,
            "source": "G"
        })
    for t in trivy_vulns:
        if t.pkg_name:
            merged_vulns.append({
                "package": t.pkg_name,
                "version": t.installed_version,
                "severity": t.severity,
                "fix_version": t.fixed_version,
                "source": "T"
            })

    profile["Vulnerabilities"] = merged_vulns
    profile["Critical Vuln Count"] = sum(1 for v in merged_vulns if v["severity"] == "Critical")
    profile["Vulnerable Dependencies %"] = round((len(merged_vulns) / (len(deps) or 1)) * 100, 2)

    # --------------- EOL (XEOL) -------------------
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

    # --------------- STATIC SCAN (SEMGREP) -------------------
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