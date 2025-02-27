import logging
from modular.shared.base_logger import BaseLogger

class GradleSnippetBuilder(BaseLogger):
    def __init__(self):
        self.logger = self.get_logger("GradleSnippetBuilder")
        self.logger.setLevel(logging.DEBUG)

    def build_snippet(self, gradle_version, task_name):
        major, _ = self._parse_major_minor(gradle_version)
        if major < 7:
            self.logger.info(f"Generating all-deps-nodupes.txt manually for Gradle {gradle_version}.")
            return self._legacy_snippet(task_name)
        else:
            self.logger.info(f"Using built-in locking for Gradle {gradle_version}.")
            return self._modern_snippet(task_name)

    def _legacy_snippet(self, task_name):
        # For Gradle <7: manually generate the dependency file at gradle/all-deps-nodupes.txt
        return f"""
task {task_name} {{
    def outputFile = file("gradle/all-deps-nodupes.txt")
    def resolvedDependencies = new LinkedHashSet<String>()

    outputs.file(outputFile)

    doLast {{
        println("Generating all-deps-nodupes.txt for Gradle <7...")

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

        outputFile.parentFile.mkdirs()
        outputFile.text = resolvedDependencies.join("\\n")
        println("all-deps-nodupes.txt generated successfully at " + outputFile.absolutePath)
    }}
}}
"""

    def _modern_snippet(self, task_name):
        # For Gradle 7+: use built-in dependency locking and then copy the generated lock file
        // to "all-deps-nodupes.txt" so that the helper can find it.
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

        println("Automatically generating dependency locks using 'dependencies --write-locks'...")
        def execResult = exec {{
            executable = project.file("gradlew").absolutePath
            args = ['dependencies', '--write-locks']
        }}
        println("Lock generation completed with exit code: " + execResult.exitValue)
        
        // Copy the generated lock file to all-deps-nodupes.txt.
        def sourceFile = file("gradle/dependency-locks/gradle.lockfile")
        def targetFile = file("gradle/all-deps-nodupes.txt")
        if (sourceFile.exists()) {{
            targetFile.parentFile.mkdirs()
            targetFile.text = sourceFile.text
            println("Copied dependency lock file to " + targetFile.absolutePath)
        }} else {{
            println("Expected dependency lock file not found at " + sourceFile.absolutePath)
        }}
    }}
}}
"""

    def _parse_major_minor(self, version_str):
        parts = version_str.split('.')
        return (int(parts[0]), int(parts[1])) if len(parts) >= 2 else (0, 0)