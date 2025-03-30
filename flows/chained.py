from prefect.automations import Automation
from prefect.events.schemas.automations import EventTrigger
from prefect.events.actions import RunDeployment

DEPLOYMENT_VERSION = "3.2.1"

AUTOMATIONS = [
    {
        "name": "metrics-to-build-tools",
        "source": "fundamental_metrics_flow",
        "target": "build_tools_flow"
    },
    {
        "name": "build-to-dependencies",
        "source": "build_tools_flow",
        "target": "dependencies_flow"
    },
    {
        "name": "dependencies-to-categories",
        "source": "dependencies_flow",
        "target": "categories_flow"
    },
    {
        "name": "categories-to-standards",
        "source": "categories_flow",
        "target": "standards_assessment_flow"
    },
    {
        "name": "standards-to-vulnerabilities",
        "source": "standards_assessment_flow",
        "target": "vulnerabilities_flow"
    }
]

def create_automations():
    automations = []
    for config in AUTOMATIONS:
        automation = Automation(
            name=config["name"],
            trigger=EventTrigger(
                expect={"prefect.flow-run.Completed"},
                match_related={
                    "prefect.resource.name": config["source"],
                    "prefect.resource.role": "flow"
                },
                posture="Reactive",
                threshold=1
            ),
            actions=[
                RunDeployment(
                    parameters={"payload": "{{ event.payload }}"},
                    deployment_name=f"{config['target']}/{config['target']}",
                )
            ]
        ).create()
        automations.append(automation)
    return automations

if __name__ == "__main__":
    create_automations()
