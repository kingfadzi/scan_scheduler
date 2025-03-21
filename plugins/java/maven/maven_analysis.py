import os
import json
import logging
from lxml import etree
from sqlalchemy.dialects.postgresql import insert
from shared.models import Session, BuildTool
from shared.execution_decorator import analyze_execution
from shared.base_logger import BaseLogger
from shared.utils import Utils

class MavenAnalyzer(BaseLogger):
    def __init__(self, logger=None):
        self.logger = logger or self.get_logger("MavenAnalyzer")
        self.logger.setLevel(logging.DEBUG)
        self.utils = Utils(logger=logger)

    @staticmethod
    def compile_xpath(expression, ns, logger):
        try:
            return etree.XPath(expression, namespaces=ns)
        except Exception as e:
            logger.error(f"Error compiling XPath expression '{expression}': {e}")
            raise

    def get_xpath_first_text(self, xpath_expr, tree):
        try:
            results = xpath_expr(tree)
            return results[0].strip() if results else None
        except Exception as e:
            self.logger.error(f"Error evaluating XPath expression: {e}")
            return None

    @analyze_execution(session_factory=Session, stage="Maven Build Analysis")
    def run_analysis(self, repo_dir, repo, run_id=None):
        self.logger.info(f"Starting Maven build analysis for repo_id: {repo['repo_id']} (repo slug: {repo['repo_slug']}).")

        repo_languages = self.utils.detect_repo_languages(repo['repo_id'])
        if "Java" not in repo_languages:
            message = f"Repo {repo['repo_id']} is not a Java project. Skipping."
            self.logger.info(message)
            return message

        if self.utils.detect_java_build_tool(repo_dir) != "Maven":
            message = f"Repo {repo['repo_id']} is Java but doesn't use Maven. Skipping."
            self.logger.info(message)
            return message

        if not os.path.exists(repo_dir):
            error_message = f"Repository directory does not exist: {repo_dir}"
            self.logger.info(error_message)
            raise FileNotFoundError(error_message)

        pom_path = os.path.join(repo_dir, "pom.xml")
        if not os.path.exists(pom_path):
            message = f"pom.xml not found in repository directory: {repo_dir}. Not a Maven project."
            self.logger.info(message)
            return message

        java_version = "Unknown"
        maven_version = "Not determined from pom.xml"

        try:
            try:
                tree = etree.parse(pom_path)
            except etree.XMLSyntaxError as e:
                self.logger.error(f"Error parsing pom.xml: XML syntax error: {e}")
                raise RuntimeError(f"Error parsing pom.xml: XML syntax error: {e}")
            except Exception as e:
                self.logger.error(f"Error parsing pom.xml: {e}")
                raise RuntimeError(e)

            ns = {"m": "http://maven.apache.org/POM/4.0.0"}

            xpath_properties = self.compile_xpath(
                "//m:properties/m:maven.compiler.source/text() | //m:properties/m:java.version/text()",
                ns, self.logger
            )
            xpath_compiler = self.compile_xpath(
                ("//m:plugin[m:artifactId='maven-compiler-plugin' and m:groupId='org.apache.maven.plugins']"
                 "/m:configuration/m:release/text() | "
                 "//m:plugin[m:artifactId='maven-compiler-plugin' and m:groupId='org.apache.maven.plugins']"
                 "/m:configuration/m:source/text()"),
                ns, self.logger
            )
            xpath_enforcer = self.compile_xpath(
                ("//m:plugin[m:artifactId='maven-enforcer-plugin' and m:groupId='org.apache.maven.plugins']"
                 "/m:configuration/m:rules/m:requireJavaVersion/m:version/text()"),
                ns, self.logger
            )
            xpath_toolchains = self.compile_xpath(
                ("//m:plugin[m:artifactId='maven-toolchains-plugin' and m:groupId='org.apache.maven.plugins']"
                 "/m:configuration/m:toolchains/m:jdk/m:version/text()"),
                ns, self.logger
            )

            java_version = (
                    self.get_xpath_first_text(xpath_compiler, tree)
                    or self.get_xpath_first_text(xpath_properties, tree)
                    or "Unknown"
            )
            maven_version = (
                    self.get_xpath_first_text(xpath_enforcer, tree)
                    or self.get_xpath_first_text(xpath_toolchains, tree)
                    or "Not determined from pom.xml"
            )
        except Exception as e:
            self.logger.error(f"Error parsing pom.xml: {e}")

        self.logger.info(f"Detected Maven build tool. Maven version: {maven_version}, Java version: {java_version}")

        session = Session()

        try:
            session.execute(
                insert(BuildTool)
                .values(
                    repo_id=repo['repo_id'],
                    tool="Maven",
                    tool_version=maven_version,
                    runtime_version=java_version,
                )
                .on_conflict_do_update(
                    index_elements=["repo_id", "tool"],
                    set_={"tool_version": maven_version, "runtime_version": java_version},
                )
            )
            session.commit()
            self.logger.info(f"Maven build analysis results successfully committed for repo_id: {repo['repo_id']}.")
        except Exception as e:
            self.logger.exception(f"Error persisting Maven build analysis results for repo_id {repo['repo_id']}: {e}")
            raise RuntimeError(e)
        finally:
            session.close()

        result = {
            "repo_id": repo['repo_id'],
            "tool": "Maven",
            "tool_version": maven_version,
            "runtime_version": java_version,
        }
        self.logger.info("Maven build analysis completed.")
        return json.dumps(result)


if __name__ == "__main__":
    repo_dir = "/tmp/log4shell-honeypot"
    repo_slug = "log4shell-honeypot"
    repo_id = "vulnerable-apps/log4shell-honeypot"

    class MockRepo:
        def __init__(self, repo_id, repo_slug):
            self.repo_id = repo_id
            self.repo_slug = repo_slug
            self.repo_name = repo_slug

    repo = MockRepo(repo_id, repo_id)
    session = Session()
    analyzer = MavenAnalyzer()
    try:
        result = analyzer.run_analysis(repo_dir=repo_dir, repo=repo, session=session, run_id="STANDALONE_RUN")
        analyzer.logger.info(f"Standalone Maven build analysis result: {result}")
    except Exception as e:
        analyzer.logger.error(f"Error during standalone Maven build analysis: {e}")
    finally:
        session.close()
