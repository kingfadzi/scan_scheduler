from prefect import flow, get_run_logger
from typing import Dict

from prefect import flow, get_run_logger
from typing import Dict

@flow(name="analyze_fundamentals", log_prints=True)
def analyze_fundamentals(repo_id: str) -> str:
    """Fundamentals analysis flow"""
    logger = get_run_logger()
    logger.info(f"Starting fundamentals analysis for {repo_id}")
    
    # Simulating success case
    return "Completed"  # ✅ Return a state string instead of a dictionary

@flow(name="analyze_vulnerabilities", log_prints=True)
def analyze_vulnerabilities(repo_id: str) -> str:
    """Vulnerability analysis flow"""
    logger = get_run_logger()
    logger.info(f"Starting vulnerability scan for {repo_id}")
    return "Completed"

@flow(name="analyze_standards", log_prints=True)
def analyze_standards(repo_id: str) -> str:
    """Standards compliance flow"""
    logger = get_run_logger()
    logger.info(f"Starting standards check for {repo_id}")
    return "Completed"

@flow(name="analyze_component_patterns", log_prints=True)
def analyze_component_patterns(repo_id: str) -> str:
    """Component patterns analysis"""
    logger = get_run_logger()
    logger.info(f"Starting component analysis for {repo_id}")
    return "Completed"
    
if __name__ == "__main__":
    # Run individual flows
    analyze_fundamentals("test_repo")
    analyze_vulnerabilities("test_repo")
    
    # Or chain multiple analyses
    repo_id = "test_repo"
    analyze_fundamentals(repo_id)
    analyze_vulnerabilities(repo_id)
    analyze_standards(repo_id)
    analyze_component_patterns(repo_id)
