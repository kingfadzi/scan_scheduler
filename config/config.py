import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:

    METRICS_DATABASE_USER = os.getenv("METRICS_DATABASE_USER", "postgres")
    METRICS_DATABASE_PASSWORD = os.getenv("METRICS_DATABASE_PASSWORD", "postgres")
    METRICS_DATABASE_HOST = os.getenv("METRICS_DATABASE_HOST", "192.168.1.188")
    METRICS_DATABASE_PORT = os.getenv("METRICS_DATABASE_PORT", "5422")
    METRICS_DATABASE_NAME = os.getenv("METRICS_DATABASE_NAME", "gitlab-usage")
    CLONED_REPOSITORIES_DIR = os.getenv("CLONED_REPOSITORIES_DIR", "./cloned_repositories")
    TRIVYIGNORE_TEMPLATE = os.getenv("TRIVYIGNORE_TEMPLATE", "./config/trivy/.trivyignore")
    SEMGREP_CONFIG_DIR = os.getenv("SEMGREP_CONFIG_DIR", "./config/semgrep")

    SEMGREP_RULESETS = os.getenv("SEMGREP_RULESETS", f"{os.environ['HOME']}/.semgrep")

    BITBUCKET_HOSTNAME = os.getenv("BITBUCKET_HOSTNAME", "bitbucket.org")
    GITLAB_HOSTNAME = os.getenv("GITLAB_HOSTNAME", "gitlab.com")

    KANTRA_RULESETS = os.getenv("KANTRA_RULESETS", f"{os.environ['HOME']}/.kantra/custom-rulesets")

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

    TRUSTSTORE_PATH = os.getenv("TRUSTSTORE_PATH", "")
    TRUSTSTORE_PASSWORD = os.getenv("TRUSTSTORE_PASSWORD", "")

    SQL_SCRIPTS_DIR = os.getenv("SQL_SCRIPTS_DIR", "./sql")

    DEFAULT_PROCESS_TIMEOUT = int(os.getenv("DEFAULT_PROCESS_TIMEOUT", 60))
