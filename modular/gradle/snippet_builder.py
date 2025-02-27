import logging
from modular.shared.base_logger import BaseLogger

class GradleSnippetBuilder(BaseLogger):
    def __init__(self):
        self.logger = self.get_logger("GradleSnippetBuilder")
        self.logger.setLevel(logging.DEBUG)

    def build_snippet(self, gradle_version, task_name):
        major, _ = self._parse_major_minor(gradle_version)
        if major < 7:
            self.logger.info(f"Generating legacy lockfile for Gradle {gradle_version}.")
            return self._legacy_lockfile_snippet(task_name)
        else:
            self.logger.info(f"Using modern locking for Gradle {gradle_version}.")
            return self._modern_lockfile_snippet(task_name)

    def _modern_lockfile_snippet(self, task_name):
        return f"""
// MODERN GRADLE (7+) LOCKING
dependencyLocking {{
    lockAllConfigurations()
    lockFile = rootProject.file("gradle.lockfile") // Ensure lockfile is in root directory
  
}}

tasks.register("{task_name}") {{
    doLast {{
        logger.lifecycle("Generating root lockfile")
        
        // Process all configurations
        for (proj in rootProject.allprojects) {{
            for (cfg in proj.configurations) {{
                if (cfg.canBeResolved) {{
                    cfg.resolutionStrategy.activateDependencyLocking()
                    try {{
                        cfg.resolve()
                    }} catch (Exception e) {{
                        logger.error("Failed locking: ${{proj.path}}:${{cfg.name}}", e)
                        throw e
                    }}
                }}
            }}
        }}
        
        // Validate lockfile location and existence
        def lockfile = rootProject.file("gradle.lockfile")
        if (!lockfile.exists()) {{
            throw new GradleException("Lockfile not generated in root directory: ${{lockfile.absolutePath}}")
        }}
        logger.lifecycle("Lockfile generated successfully at: ${{lockfile.absolutePath}}")
    }}
}}

// Buildscript locking
buildscript {{
    dependencyLocking {{
        lockFile = rootProject.file("gradle.buildscript.lockfile") // Separate lockfile for buildscript
    }}
    for (cfg in configurations) {{
        if (cfg.canBeResolved) {{
            cfg.resolutionStrategy.activateDependencyLocking()
        }}
    }}
}}
"""

    def _legacy_lockfile_snippet(self, task_name):
        return f"""
// LEGACY GRADLE (<7) LOCKING
task {task_name} {{
    def lockfile = rootProject.file("gradle.lockfile") // Ensure lockfile is in root directory
    def deps = new LinkedHashSet<String>()
    
    outputs.file(lockfile)
    
    doLast {{
        logger.lifecycle("Generating legacy root lockfile")
        
        // Collect all dependencies
        for (proj in rootProject.allprojects) {{
            for (cfg in proj.configurations) {{
                if (cfg.canBeResolved) {{
                    for (art in cfg.resolvedConfiguration.resolvedArtifacts) {{
                        def mod = art.moduleVersion.id
                        deps.add("${{mod.group}}:${{mod.name}}:${{mod.version}}")
                    }}
                }}
            }}
        }}
        
        // Write to root file
        lockfile.text = deps.sort().join("\\n")
        logger.lifecycle("Lockfile entries: ${{deps.size()}}")
        
        // Validate lockfile location and existence
        if (!lockfile.exists()) {{
            throw new GradleException("Lockfile not generated in root directory: ${{lockfile.absolutePath}}")
        }}
        logger.lifecycle("Lockfile generated successfully at: ${{lockfile.absolutePath}}")
    }}
}}

// Enforce lockfile presence
gradle.projectsEvaluated {{
    tasks.named("check") {{
        dependsOn("{task_name}")
        doLast {{
            def lockfile = rootProject.file("gradle.lockfile")
            if (!lockfile.exists()) {{
                throw new GradleException("Missing root lockfile: ${{lockfile.absolutePath}}")
            }}
            logger.lifecycle("Lockfile validated at: ${{lockfile.absolutePath}}")
        }}
    }}
}}
"""

    def _parse_major_minor(self, version_str):
        parts = version_str.split('.')
        return (int(parts[0]), int(parts[1])) if len(parts) >= 2 else (0, 0)
