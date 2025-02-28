import os
import logging
import subprocess
import signal
from modular.shared.base_logger import BaseLogger
from config.config import Config
from modular.gradle.environment_manager import GradleEnvironmentManager
import traceback

class GradleRunner(BaseLogger):

    def __init__(self, logger=None):
        if logger is None:
            self.logger = self.get_logger("GradleRunner")
        else:
            self.logger = logger

        self.logger.setLevel(logging.DEBUG)
        self.environment_manager = GradleEnvironmentManager()

    def run(self, cmd, cwd, gradle_version, check=True):
        if not gradle_version:
            self.logger.error("Gradle version is missing or invalid. Aborting Gradle execution.")
            return None

        java_home = self.environment_manager._select_java_home(gradle_version)
        env = self._setup_env(java_home)

        self.logger.debug(f"Setting JAVA_HOME for Gradle: {env['JAVA_HOME']}")
        self.logger.info(f"Running Gradle command: {' '.join(cmd)} in {cwd}")

        proc = None
        try:
            # Launch the process in a new session so all children are grouped together.
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True
            )
            stdout, stderr = proc.communicate(timeout=180)
            retcode = proc.returncode

            if check and retcode != 0:
                raise subprocess.CalledProcessError(retcode, cmd, stdout, stderr)

            self.logger.debug(f"Return code: {retcode}")
            if stdout:
                self.logger.debug(f"Stdout:\n{stdout}")
            if stderr:
                self.logger.debug(f"Stderr:\n{stderr}")

            return subprocess.CompletedProcess(cmd, retcode, stdout, stderr)

        except subprocess.TimeoutExpired:
            if proc:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                stdout, stderr = proc.communicate()
            self.logger.error("Timeout after 180 seconds:")
            self.logger.error(f"Captured STDOUT:\n{stdout}")
            self.logger.error(f"Captured STDERR:\n{stderr}")
            return None

        except subprocess.CalledProcessError as cpe:
            self.logger.error(f"Command failed with exit code {cpe.returncode}:")
            self.logger.error(f"STDOUT:\n{cpe.stdout}")
            self.logger.error(f"STDERR:\n{cpe.stderr}")
            self.logger.error(f"Traceback:\n{traceback.format_exc()}")
            return None

        except Exception as ex:
            self.logger.error(f"Unexpected error: {ex}")
            self.logger.error(f"Traceback:\n{traceback.format_exc()}")
            return None

    def _setup_env(self, java_home):
        env = os.environ.copy()
        env.pop("JAVA_HOME", None)  # Clear any pre-existing JAVA_HOME
        env["JAVA_HOME"] = java_home
        env["GRADLE_OPTS"] = self._build_gradle_opts(env.get("GRADLE_OPTS", ""))
        self.logger.debug(f"Environment setup for Gradle: JAVA_HOME={env['JAVA_HOME']}")
        return env

    def _build_gradle_opts(self, existing_opts):
        opts = [existing_opts] if existing_opts else []
        if getattr(Config, "HTTP_PROXY_HOST", None) and getattr(Config, "HTTP_PROXY_PORT", None):
            opts.append(f"-Dhttp.proxyHost={Config.HTTP_PROXY_HOST}")
            opts.append(f"-Dhttp.proxyPort={Config.HTTP_PROXY_PORT}")
        if getattr(Config, "TRUSTSTORE_PATH", None):
            opts.append(f"-Djavax.net.ssl.trustStore={Config.TRUSTSTORE_PATH}")
        if getattr(Config, "TRUSTSTORE_PASSWORD", None):
            opts.append(f"-Djavax.net.ssl.trustStorePassword={Config.TRUSTSTORE_PASSWORD}")
        return " ".join(opts).strip()
