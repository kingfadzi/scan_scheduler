import logging
from modular.shared.base_logger import BaseLogger

class GradleSnippetBuilder(BaseLogger):
    def __init__(self):
        self.logger = self.get_logger("GradleSnippetBuilder")
        self.logger.setLevel(logging.DEBUG)

    def build_snippet(self, gradle_version, task_name):
        major, _ = self._parse_major_minor(gradle_version)
        if major < 7:
            self.logger.info(f"Generating unified lockfile for legacy Gradle {gradle_version}")
            return self._legacy_lockfile_snippet(task_name)
        else:
            self.logger.info(f"Using native locking for Gradle {gradle_version}")
            return self._modern_lockfile_snippet(task_name)

    def _legacy_lockfile_snippet(self, task_name):
        return f"""
task {task_name} {{
    def lockfile = file("gradle.lockfile")
    def strictDependencies = new LinkedHashSet<String>()
    
    outputs.file(lockfile)

    doLast {{
        logger.lifecycle("Generating legacy-style gradle.lockfile")
        
        allprojects {{ proj ->
            proj.configurations.each {{ cfg ->
                try {{
                    if (cfg.canBeResolved) {{
                        cfg.resolvedConfiguration.firstLevelModuleDependencies.each {{ dep ->
                            def coord = "${{dep.moduleGroup}}:${{dep.moduleName}}:${{dep.moduleVersion}} (strict)"
                            strictDependencies.add(coord)
                        }}
                    }}
                }} catch (Exception e) {{
                    logger.error("Lockfile generation error in ${{proj.name}}:", e)
                }}
            }}
        }}
        
        lockfile.parentFile.mkdirs()
        lockfile.text = strictDependencies.sort().join("\\n")
        logger.lifecycle("Generated legacy lockfile at ${{lockfile.absolutePath}}")
    }}
}}
"""

    def _modern_lockfile_snippet(self, task_name):
        return f"""
dependencyLocking {{
    lockAllConfigurations()
    lockFile = file("gradle.lockfile")
}}

tasks.register("{task_name}") {{
    doLast {{
        logger.lifecycle("Generating modern gradle.lockfile")
        
        gradle.rootProject.allprojects {{ proj ->
            proj.configurations.each {{ cfg ->
                if (cfg.canBeResolved) {{
                    cfg.resolutionStrategy.activateDependencyLocking()
                }}
            }}
        }}

        def result = exec {{
            executable = project.file("gradlew").absolutePath
            args = ["dependencies", "--write-locks", "--update-locks", "*"]
        }}
        
        if (result.exitValue != 0) {{
            throw new GradleException("Lockfile generation failed with exit code ${{result.exitValue}}")
        }}
        
        logger.lifecycle("Successfully generated gradle.lockfile")
    }}
}}
"""

    def _parse_major_minor(self, version_str):
        clean_version = version_str.split('-')[0]
        parts = clean_version.split('.')
        try:
            return (int(parts[0]), int(parts[1])) if len(parts) >= 2 else (0, 0)
        except ValueError:
            self.logger.warning(f"Invalid version format: {version_str}")
            return (0, 0)
