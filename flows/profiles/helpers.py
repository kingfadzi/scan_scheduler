from shared.models import BuildTool

def extract_runtime_version(session, repo_id):

    build_tools = session.query(BuildTool).filter_by(repo_id=repo_id).all()

    if not build_tools:
        return None

    parts = []
    for tool in build_tools:
        tool_name = (tool.tool or "Unknown").lower()
        runtime_version = tool.runtime_version or "Unknown"

        if tool_name in ["gradle", "maven"]:
            language = "Java"
        elif tool_name in ["npm", "yarn"]:
            language = "Node.js"
        elif tool_name in ["poetry", "pipenv", "pip"]:
            language = "Python"
        elif tool_name in ["go"]:
            language = "Go"
        else:
            language = "Unknown"

        parts.append(f"{language}:{runtime_version}")

    return ", ".join(parts)

def classify_repo(repo_size_bytes: float, total_loc: int) -> str:
    if repo_size_bytes is None:
        repo_size_bytes = 0
    if total_loc is None:
        total_loc = 0
    if total_loc < 100:
        return "Empty/Minimal" if repo_size_bytes < 1_000_000 else "Docs/Data"
    if repo_size_bytes < 1_000_000:
        return "Tiny"
    if repo_size_bytes < 10_000_000:
        return "Small"
    if repo_size_bytes < 100_000_000:
        return "Medium"
    if repo_size_bytes < 1_000_000_000:
        return "Large"
    return "Massive"

def infer_build_tool(syft_dependencies):
    build_tool = None
    for dependency in syft_dependencies:
        name = (dependency.package_name or "").lower()
        package_type = (dependency.package_type or "").lower()
        version = (dependency.version or "").strip()
        locations = (dependency.locations or "").lower()

        if "gradle-wrapper" in name:
            build_tool = f"gradle-wrapper:{version}" if version else "gradle-wrapper"
            break
        if "maven-wrapper" in name:
            build_tool = f"maven-wrapper:{version}" if version else "maven-wrapper"
            break
        if package_type == "java-archive" and "pom.xml" in locations:
            build_tool = "maven"
        if not build_tool:
            if package_type == "python":
                build_tool = "python"
            elif package_type == "npm":
                build_tool = "node"
            elif package_type == "go-module":
                build_tool = "go"
            elif package_type == "gem":
                build_tool = "ruby"
    return build_tool or "Unknown"
