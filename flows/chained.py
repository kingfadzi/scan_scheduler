from prefect import flow
from prefect.automations import Automation
from prefect.events.schemas.automations import EventTrigger
from prefect.events.actions import RunDeployment
from prefect.client import get_client
import asyncio

DEPLOYMENT_VERSION = "3.2.1"
WORK_POOL_NAME = "fundamentals-pool"

# List of flow deployments in execution order
FLOW_SEQUENCE = [
    "fundamental_metrics_flow",
    "build_tools_flow",
    "dependencies_flow",
    "categories_flow",
    "standards_assessment_flow",
    "vulnerabilities_flow"
]

async def get_deployment_id(flow_name: str) -> str:
    """Get deployment ID by flow name"""
    async with get_client() as client:
        deployment = await client.read_deployment_by_name(
            f"{flow_name}/{flow_name}-deployment"
        )
        return str(deployment.id)

async def create_chain_automation(source: str, target: str) -> Automation:
    """Create automation between two flows"""
    target_deployment_id = await get_deployment_id(target)
    
    return Automation(
        name=f"{source}-to-{target}",
        trigger=EventTrigger(
            expect={"prefect.flow-run.Completed"},
            match_related={
                "prefect.resource.name": source,
                "prefect.resource.role": "flow"
            },
            posture="Reactive",
            threshold=1
        ),
        actions=[
            RunDeployment(
                parameters={"payload": "{{ event.payload }}"},
                deployment_id=target_deployment_id
            )
        ]
    )

async def main():
    # Create automations for each consecutive pair
    automations = []
    for i in range(len(FLOW_SEQUENCE)-1):
        source = FLOW_SEQUENCE[i]
        target = FLOW_SEQUENCE[i+1]
        
        automation = await create_chain_automation(source, target)
        automation.create()
        automations.append(automation)
        print(f"Created automation: {source} → {target}")

if __name__ == "__main__":
    asyncio.run(main())
