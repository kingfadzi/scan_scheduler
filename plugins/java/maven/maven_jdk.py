import re
import logging
from pathlib import Path
import xml.etree.ElementTree as ET

from shared.language_required_decorator import language_required
from shared.models import Session, BuildTool
from shared.execution_decorator import analyze_execution
from shared.base_logger import BaseLogger
from shared.utils import Utils
from sqlalchemy.dialects.postgresql import insert


class MavenJdkAnalyzer(BaseLogger):

    def __init__(self, logger=None, run_id=None):
        super().__init__(logger=logger, run_id=run_id)
        self.logger.setLevel(logging.DEBUG)

        self.utils = Utils(logger=self.logger)


    @analyze_execution(session_factory=Session, stage="Maven Build Analysis")
    @language_required("java")
    def run_analysis(self, repo_dir, repo, run_id=None):
        repo_path = Path(repo_dir).resolve()
        if not repo_path.exists():
            self.logger.error(f"Invalid repo path: {repo_dir}")
            raise FileNotFoundError(f"{repo_dir} does not exist")

        self.logger.debug(f"Analyzing repo: {repo['repo_id']} at {repo_path}")
        results = []
        session = Session()

        try:
            root_pom = repo_path / "pom.xml"
            if root_pom.exists():
                self.logger.debug("Detected root pom.xml. Treating as single Maven project.")
                maven_version = self.extract_maven_version(repo_path)
                java_version = self.extract_jdk_version(repo_path)
                self.utils.persist_build_tool("maven", repo["repo_id"], maven_version, java_version)
                results.append((repo["repo_id"], maven_version, java_version))
            else:
                self.logger.debug("No root pom.xml found. Scanning for all pom.xml files.")
                seen = set()
                for pom in repo_path.rglob("pom.xml"):
                    project_dir = pom.parent
                    if project_dir in seen:
                        continue
                    seen.add(project_dir)
                    self.logger.debug(f"Processing project at {project_dir}")
                    maven_version = self.extract_maven_version(project_dir)
                    java_version = self.extract_jdk_version(project_dir)
                    project_repo_id = f"{repo['repo_id']}/{project_dir.relative_to(repo_path).as_posix()}"
                    self.utils.persist_build_tool("maven", repo["repo_id"], maven_version, java_version)
                    results.append((project_repo_id, maven_version, java_version))
            session.commit()
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error analyzing repo {repo['repo_id']}: {e}", exc_info=True)
            raise
        finally:
            session.close()

        return results


    def extract_maven_version(self, repo_path: Path) -> str:
        props_file = repo_path / ".mvn" / "wrapper" / "maven-wrapper.properties"
        if props_file.exists():
            self.logger.debug(f"Reading Maven wrapper properties: {props_file}")
            for line in props_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("distributionUrl"):
                    match = re.search(r"apache-maven-([0-9.]+)-bin", line)
                    if match:
                        version = match.group(1)
                        self.logger.debug(f"Found Maven version: {version}")
                        return version
        self.logger.debug("No Maven wrapper found. Returning 'unspecified'.")
        return "unspecified"

    def extract_jdk_version(self, repo_path: Path) -> str:
        pom_file = repo_path / "pom.xml"
        if pom_file.exists():
            try:
                tree = ET.parse(pom_file)
                root = tree.getroot()
                ns = {"m": "http://maven.apache.org/POM/4.0.0"}
                for plugin in root.findall(".//m:plugin", ns):
                    artifact = plugin.find("m:artifactId", ns)
                    if artifact is not None and artifact.text == "maven-compiler-plugin":
                        config = plugin.find("m:configuration", ns)
                        if config is not None:
                            release = config.find("m:release", ns)
                            source = config.find("m:source", ns)
                            if release is not None:
                                version = release.text.strip()
                                self.logger.debug(f"Found JDK release version: {version}")
                                return version
                            if source is not None:
                                version = source.text.strip()
                                self.logger.debug(f"Found JDK source version: {version}")
                                return version
            except Exception as e:
                self.logger.warning(f"Failed to parse JDK version from {pom_file}: {e}")

        jvm_config = repo_path / ".mvn" / "jvm.config"
        if jvm_config.exists():
            self.logger.debug(f"Reading JDK version from: {jvm_config}")
            content = jvm_config.read_text(encoding="utf-8")
            match = re.search(r"--release\s+(\d+)", content)
            if match:
                version = match.group(1)
                self.logger.debug(f"Found JDK version in jvm.config: {version}")
                return version

        self.logger.debug("No JDK version info found. Returning 'unspecified'.")
        return "unspecified"


if __name__ == "__main__":
    repo_dir = "/tmp/maven-modular"
    repo = {
        "repo_id": "maven-modular",
        "repo_slug": "maven-modular",
        "repo_name": "maven-modular",
    }
    analyzer = MavenJdkAnalyzer()
    try:
        results = analyzer.run_analysis(repo_dir=repo_dir, repo=repo, run_id="STANDALONE_RUN")
        for repo_id_value, maven_version, java_version in results:
            print(f"{repo_id_value}: Maven={maven_version}, JDK={java_version}")
    except Exception as e:
        analyzer.logger.error(f"Standalone run failed: {e}", exc_info=True)
