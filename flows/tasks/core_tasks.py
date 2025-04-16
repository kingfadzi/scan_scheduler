from prefect import task, get_run_logger
from prefect.cache_policies import NO_CACHE
from plugins.core.checkov_analysis import CheckovAnalyzer
from plugins.core.iac_analysis import IacComponentAnalyzer
from plugins.core.semgrep_analysis import SemgrepAnalyzer
from plugins.core.gitlog_analysis import GitLogAnalyzer
from plugins.core.go_enry_analysis import GoEnryAnalyzer
from plugins.core.lizard_analysis import LizardAnalyzer
from plugins.core.cloc_analysis import ClocAnalyzer
from plugins.core.trivy_analysis import TrivyAnalyzer
from plugins.core.syft_analysis import SyftAnalyzer
from plugins.core.grype_analysis import GrypeAnalyzer
from plugins.core.xeol_analysis import XeolAnalyzer

from plugins.core.syft_dependency_analysis import SyftDependencyAnalyzer
from shared.models import IacComponent


@task(name="Category Analysis Task", cache_policy=NO_CACHE)
async def run_catgeory_analysis_task(run_id):
    logger = get_run_logger()
    try:
        logger.info("[Component Patterns] Starting Category analysis")
        analyzer = CategoryAnalyzer(logger=logger, run_id=run_id)
        analyzer.run_analysis()
        logger.info("[Component Patterns] Completed Category analysis.")
    except Exception as exc:
        logger.exception("Error during Category analysis")
        raise exc

@task(name="Run Checkov Analysis Task", cache_policy=NO_CACHE)
async def run_checkov_analysis_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    try:
        logger.info(f"[Standards Assessment] Starting Checkov analysis for repository: {repo['repo_id']}")
        analyzer = CheckovAnalyzer(logger=logger, run_id=run_id)
        analyzer.run_analysis(repo_dir=repo_dir, repo=repo)
        logger.info(f"[Standards Assessment] Completed Checkov analysis for repository: {repo['repo_id']}")
    except Exception as exc:
        logger.exception("Error during Checkov analysis")
        raise exc

@task(name="Run Semgrep Analysis Task", cache_policy=NO_CACHE)
async def run_semgrep_analysis_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    try:
        logger.info(f"[Standards Assessment] Starting Semgrep analysis for repository: {repo['repo_id']}")
        analyzer = SemgrepAnalyzer(logger=logger, run_id=run_id)
        analyzer.run_analysis(repo_dir=repo_dir, repo=repo)
        logger.info(f"[Standards Assessment] Completed Semgrep analysis for repository: {repo['repo_id']}")
    except Exception as exc:
        logger.exception("Error during Semgrep analysis")
        raise exc

@task(name="Run Lizard Analysis Task", cache_policy=NO_CACHE)
async def run_lizard_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    try:
        logger.info(f"[Fundamental Metrics] Starting Lizard analysis for repository: {repo['repo_id']}")
        analyzer = LizardAnalyzer(logger=logger, run_id=run_id)
        analyzer.run_analysis(repo_dir=repo_dir, repo=repo)
        logger.info(f"[Fundamental Metrics] Completed Lizard analysis for repository: {repo['repo_id']}")
    except Exception as exc:
        logger.exception("Error during Lizard analysis")
        raise exc

@task(name="Run CLOC Analysis Task", cache_policy=NO_CACHE)
async def run_cloc_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    try:
        logger.info(f"[Fundamental Metrics] Starting CLOC analysis for repository: {repo['repo_id']}")
        analyzer = ClocAnalyzer(logger=logger, run_id=run_id)
        analyzer.run_analysis(repo_dir=repo_dir, repo=repo)
        logger.info(f"[Fundamental Metrics] Completed CLOC analysis for repository: {repo['repo_id']}")
    except Exception as exc:
        logger.exception("Error during CLOC analysis")
        raise exc

@task(name="Run GoEnry Analysis Task", cache_policy=NO_CACHE)
async def run_goenry_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    try:
        logger.info(f"[Fundamental Metrics] Starting GoEnry analysis for repository: {repo['repo_id']}")
        analyzer = GoEnryAnalyzer(logger=logger, run_id=run_id)
        analyzer.run_analysis(repo_dir=repo_dir, repo=repo)
        logger.info(f"[Fundamental Metrics] Completed GoEnry analysis for repository: {repo['repo_id']}")
    except Exception as exc:
        logger.exception("Error during GoEnry analysis")
        raise exc

@task(name="Run GitLog Analysis Task", cache_policy=NO_CACHE)
async def run_gitlog_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    try:
        logger.info(f"[Fundamental Metrics] Starting GitLog analysis for repository: {repo['repo_id']}")
        analyzer = GitLogAnalyzer(logger=logger, run_id=run_id)
        analyzer.run_analysis(repo_dir=repo_dir, repo=repo)
        logger.info(f"[Fundamental Metrics] Completed GitLog analysis for repository: {repo['repo_id']}")
    except Exception as exc:
        logger.exception("Error during GitLog analysis")
        raise exc

@task(name="Run Trivy Analysis Task", cache_policy=NO_CACHE)
async def run_trivy_analysis_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    try:
        logger.info(f"[Vulnerabilities] Starting Trivy analysis for repository: {repo['repo_id']}")
        analyzer = TrivyAnalyzer(logger=logger, run_id=run_id)
        analyzer.run_analysis(repo_dir=repo_dir, repo=repo)
        logger.info(f"[Vulnerabilities] Completed Trivy analysis for repository: {repo['repo_id']}")
    except Exception as exc:
        logger.exception("Error during Trivy analysis")
        raise exc

@task(name="Syft Analysis Task", cache_policy=NO_CACHE)
async def run_syft_analysis_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    try:
        logger.info(f"[Component Patterns] Starting Syft analysis for repository: {repo['repo_id']}")
        analyzer = SyftAnalyzer(logger=logger, run_id=run_id)
        analyzer.run_analysis(repo_dir=repo_dir, repo=repo)
        logger.info(f"[Component Patterns] Completed Syft analysis for repository: {repo['repo_id']}")
    except Exception as exc:
        logger.exception("Error during Syft analysis")
        raise exc

@task(name="Run Grype Analysis Task", cache_policy=NO_CACHE)
async def run_grype_analysis_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    try:
        logger.info(f"[Component Patterns] Starting Grype analysis for repository: {repo['repo_id']}")
        analyzer = GrypeAnalyzer(logger=logger, run_id=run_id)
        analyzer.run_analysis(repo_dir=repo_dir, repo=repo)
        logger.info(f"[Component Patterns] Completed Grype analysis for repository: {repo['repo_id']}")
    except Exception as exc:
        logger.exception("Error during Grype analysis")
        raise exc

@task(name="Run Xeol Analysis Task", cache_policy=NO_CACHE)
async def run_xeol_analysis_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    try:
        logger.info(f"[Component Patterns] Starting Xeol analysis for repository: {repo['repo_id']}")
        analyzer = XeolAnalyzer(logger=logger, run_id=run_id)
        analyzer.run_analysis(repo_dir=repo_dir, repo=repo)
        logger.info(f"[Component Patterns] Completed Xeol analysis for repository: {repo['repo_id']}")
    except Exception as exc:
        logger.exception("Error during Xeol analysis")
        raise exc
        
        
@task(name="Run Syft Dependency Analysis Task", cache_policy=NO_CACHE)
async def run_syft_dependency_analysis_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    try:
        logger.info(f"[Component Patterns] Starting Syft dependency analysis for repository: {repo['repo_id']}")
        analyzer = SyftDependencyAnalyzer(logger=logger, run_id=run_id)
        analyzer.run_analysis(repo_dir=repo_dir, repo=repo)
        logger.info(f"[Component Patterns] Completed Syft dependency analysis for repository: {repo['repo_id']}")
    except Exception as exc:
        logger.exception("Error during Syft dependency analysis")
        raise exc

@task(name="Run IaC Component Analysis Task", cache_policy=NO_CACHE)
async def run_iac_component_analysis_task(repo_dir, repo, run_id):
    logger = get_run_logger()
    try:
        logger.info(f"[Iac Components] Starting IaC component analysis for repository: {repo['repo_id']}")
        analyzer = IacComponentAnalyzer(logger=logger, run_id=run_id)
        analyzer.run_analysis(repo_dir=repo_dir, repo=repo)
        logger.info(f"[Iac Components] Completed IaC component analysis for repository: {repo['repo_id']}")
    except Exception as exc:
        logger.exception("Error during IaC component analysis")
        raise exc