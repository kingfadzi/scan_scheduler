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
