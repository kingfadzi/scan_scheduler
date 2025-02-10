import logging
from modular.shared.base_logger import BaseLogger

class GradleSnippetBuilder(BaseLogger):
    def __init__(self):
        self.logger = self.get_logger("GradleSnippetBuilder")
        self.logger.setLevel(logging.DEBUG)

    def build_snippet(self, gradle_version, task_name):
        major, _ = self._parse_major_minor(gradle_version)
        if major < 7:
            self.logger.info(f"Generating gradle.lockfile manually for Gradle {gradle_version}.")
            return self._legacy_snippet(task_name)
        else:
            self.logger.info(f"Using built-in locking for Gradle {gradle_version}.")
            return self._modern_snippet(task_name)

    def _legacy_snippet(self, task_name):
        """ Creates gradle.lockfile manually for Gradle <7 """
        return f"""
task {task_name} {{
    def lockFile = file("gradle/gradle.lockfile")
    def resolvedDependencies = new LinkedHashSet<String>()

    outputs.file(lockFile)

    doLast {{
        println("Generating gradle.lockfile for Gradle <7...")

        project.allprojects {{ proj ->
            proj.configurations.each {{ cfg ->
                try {{
                    if (cfg.metaClass.hasProperty(cfg, 'canBeResolved') && cfg.canBeResolved) {{
                        def deps = cfg.resolvedConfiguration.lenientConfiguration.allModuleDependencies
                        deps.each {{ dep ->
                            def coordinate = "${{dep.moduleGroup}}:${{dep.moduleName}}:${{dep.moduleVersion}}"
                            resolvedDependencies.add(coordinate)
                        }}
                    }}
                }} catch (Exception e) {{
                    println("Error resolving dependencies in ${{proj.name}}: ${{e.message}}")
                }}
            }}
        }}

        lockFile.parentFile.mkdirs()
        lockFile.text = resolvedDependencies.join("\\n")
        println("gradle.lockfile generated successfully.")
    }}
}}
"""

    def _modern_snippet(self, task_name):
        """ Uses Gradle's built-in locking for Gradle 7+ """
        return f"""
tasks.register("{task_name}") {{
    doLast {{
        println("Using Gradle's built-in dependency locking...")
        
        gradle.rootProject.allprojects.each {{ proj ->
            proj.configurations.each {{ cfg ->
                if (cfg.metaClass.hasProperty(cfg, 'canBeResolved') && cfg.canBeResolved) {{
                    cfg.resolutionStrategy.activateDependencyLocking()
                }}
            }}
        }}

        println("Run './gradlew dependencies --write-locks' to generate gradle.lockfile.")
    }}
}}
"""

    def _parse_major_minor(self, version_str):
        """ Parses major version from a Gradle version string. """
        parts = version_str.split('.')
        return (int(parts[0]), int(parts[1])) if len(parts) >= 2 else (0, 0)