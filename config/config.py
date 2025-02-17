import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:

    RULESET_MAPPING_FILE = os.getenv("RULESET_MAPPING_FILE", "./tools/semgrep/language_ruleset_map.txt")
    METRICS_DATABASE_USER = os.getenv("METRICS_DATABASE_USER", "postgres")
    METRICS_DATABASE_PASSWORD = os.getenv("METRICS_DATABASE_PASSWORD", "postgres")
    METRICS_DATABASE_HOST = os.getenv("METRICS_DATABASE_HOST", "192.168.1.188")
    METRICS_DATABASE_PORT = os.getenv("METRICS_DATABASE_PORT", "5422")
    METRICS_DATABASE_NAME = os.getenv("METRICS_DATABASE_NAME", "gitlab-usage")
    CLONED_REPOSITORIES_DIR = os.getenv("CLONED_REPOSITORIES_DIR", "./cloned_repositories")
    TRIVYIGNORE_TEMPLATE = os.getenv("TRIVYIGNORE_TEMPLATE", "./config/trivy/.trivyignore")
    SEMGREP_CONFIG_DIR = os.getenv("SEMGREP_CONFIG_DIR", "./config/semgrep")

    SEMGREP_RULESET_DIR = os.getenv("SEMGREP_RULESET_DIR", f"{os.environ['HOME']}/.semgrep")

    BITBUCKET_HOSTNAME = os.getenv("BITBUCKET_HOSTNAME", "bitbucket.org")
    GITLAB_HOSTNAME = os.getenv("GITLAB_HOSTNAME", "gitlab.com")

    KANTRA_RULESETS = os.getenv("KANTRA_RULESETS", f"{os.environ['HOME']}/.kantra/custom-custom-rulesets")
    
    KANTRA_OUTPUT_ROOT = os.getenv("KANTRA_OUTPUT_ROOT", "./output")

    JAVA_HOME = os.getenv("JAVA_HOME", "/opt/homebrew/opt/openjdk")
    JAVA_8_HOME = os.getenv("JAVA_8_HOME", "/Library/Java/JavaVirtualMachines/temurin-8.jdk/Contents/Home")
    JAVA_11_HOME = os.getenv("JAVA_11_HOME", "/opt/homebrew/opt/openjdk@11")
    JAVA_17_HOME = os.getenv("JAVA_17_HOME", "/Library/Java/JavaVirtualMachines/openjdk-17.jdk/Contents/Home")
    JAVA_21_HOME = os.getenv("JAVA_21_HOME", "/opt/homebrew/opt/openjdk")

    HTTP_PROXY_HOST = os.getenv("HTTP_PROXY_HOST", "")
    HTTP_PROXY_PORT = os.getenv("HTTP_PROXY_PORT", "")
    HTTP_PROXY_USER = os.getenv("HTTP_PROXY_USER", "")
    HTTP_PROXY_PASSWORD = os.getenv("HTTP_PROXY_PASSWORD", "")
    NO_PROXY = os.getenv("NO_PROXY", "")

    HTTPS_PROXY_HOST = os.getenv("HTTPS_PROXY_HOST", "")
    HTTPS_PROXY_PORT = os.getenv("HTTPS_PROXY_PORT", "")
    HTTPS_PROXY_USER = os.getenv("HTTPS_PROXY_USER", "")
    HTTPS_PROXY_PASSWORD = os.getenv("HTTPS_PROXY_PASSWORD", "")

    TRUSTSTORE_PATH = os.getenv("TRUSTSTORE_PATH", "")
    TRUSTSTORE_PASSWORD = os.getenv("TRUSTSTORE_PASSWORD", "")

    SQL_SCRIPTS_DIR = os.getenv("SQL_SCRIPTS_DIR", "./sql")

    DEFAULT_PROCESS_TIMEOUT = int(os.getenv("DEFAULT_PROCESS_TIMEOUT", 60))
