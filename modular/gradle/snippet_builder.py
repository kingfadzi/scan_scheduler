import logging
from modular.shared.base_logger import BaseLogger

class GradleSnippetBuilder(BaseLogger):
    def __init__(self):
        self.logger = self.get_logger("GradleSnippetBuilder")
        self.logger.setLevel(logging.DEBUG)

    def build_snippet(self, gradle_version, task_name):
        major, minor = self._parse_major_minor(gradle_version)
        if major < 7:
            self.logger.debug(f"Using legacy snippet for Gradle {gradle_version}")
            return self._legacy_snippet(task_name)
        else:
            self.logger.debug(f"Using modern snippet for Gradle {gradle_version}")
            return self._modern_snippet(task_name)

    def _legacy_snippet(self, task_name):
        return f"""
task {task_name} {{
    outputs.upToDateWhen {{ false }}

    doLast {{
        def outputFile = new File("${{rootProject.buildDir}}/reports/all-deps-nodupes.txt")
        outputFile.parentFile.mkdirs()
        def visited = new HashSet<String>()
        def visitDependencyTree = {{ d ->
            def id = "${{d.moduleGroup}}:${{d.moduleName}}:${{d.moduleVersion}}"
            if (visited.add(id)) {{
                d.children.each {{ visitDependencyTree(it) }}
            }}
        }}

        project.allprojects {{ proj ->
            proj.configurations.each {{ cfg ->
                try {{
                    if (cfg.metaClass.hasProperty(cfg, 'canBeResolved') && !cfg.canBeResolved) {{
                        println("Skipping ${{cfg.name}} in ${{proj.name}} (canBeResolved=false).")
                        return
                    }}
                    // Old approach using resolvedConfiguration
                    def deps = cfg.resolvedConfiguration.lenientConfiguration.allModuleDependencies
                    deps.each {{ dep -> visitDependencyTree(dep) }}
                }} catch (Exception e) {{
                    println("Error resolving ${{cfg.name}} in ${{proj.name}}: ${{e.message}}")
                }}
            }}
        }}

        outputFile.text = visited.join("\\n")
        println("Dependencies written to: ${{outputFile.absolutePath}}")
        println("Total unique dependencies: ${{visited.size()}}")
    }}
}}
"""

    def _modern_snippet(self, task_name):
        return f"""
task {task_name} {{
    def allProjectsList = gradle.rootProject.allprojects
    def outputFileProvider = layout.buildDirectory.file("reports/all-deps-nodupes.txt")

    outputs.file(outputFileProvider)

    doLast {{
        def visited = new LinkedHashSet<String>()
        def outputFile = outputFileProvider.get().asFile
        outputFile.parentFile.mkdirs()

        allProjectsList.each {{ proj ->
            proj.configurations.each {{ cfg ->
                try {{
                    if (cfg.metaClass.hasProperty(cfg, 'canBeResolved') && !cfg.canBeResolved) {{
                        println("Skipping ${{cfg.name}} in ${{proj.name}} (canBeResolved=false).")
                        return
                    }}
                    def resolutionResult = cfg.incoming.resolutionResult
                    resolutionResult.allComponents.each {{ comp ->
                        if (comp.id instanceof org.gradle.api.artifacts.component.ModuleComponentIdentifier) {{
                            def mci = comp.id as org.gradle.api.artifacts.component.ModuleComponentIdentifier
                            def coordinate = "${{mci.group}}:${{mci.module}}:${{mci.version}}"
                            visited.add(coordinate)
                        }}
                    }}
                }} catch (Exception e) {{
                    println("Error resolving ${{cfg.name}} in ${{proj.name}}: ${{e.message}}")
                }}
            }}
        }}

        outputFile.text = visited.join("\\n")
        println("Dependencies written to: ${{outputFile.absolutePath}}")
        println("Total unique dependencies: ${{visited.size()}}")
    }}
}}
"""

    def _parse_major_minor(self, version_str):
        parts = version_str.split('.')
        if len(parts) < 2:
            return (0, 0)
        try:
            return (int(parts[0]), int(parts[1]))
        except ValueError:
            return (0, 0)
