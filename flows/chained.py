from prefect import flow
import asyncio
from standards import standards_assessment_flow
from fundamentals import fundamental_metrics_flow
from vulnerabilities import vulnerabilities_flow
from components import component_patterns_flow
from modular.shared.utils import generate_main_flow_run_name


@flow(name="Chained Main Flow", flow_run_name=generate_main_flow_run_name)
async def chained_flow(payload: dict):
    print("Starting Chained Main Flow...")

    await fundamental_metrics_flow(payload)
    await component_patterns_flow(payload)
    await standards_assessment_flow(payload)
    await vulnerabilities_flow(payload)

    print("Chained Main Flow completed.")

# For testing purposes.
if __name__ == "__main__":
    example_payload = {
        "payload": {
            "host_name": ["github.com"],
            "activity_status": ["ACTIVE"]
        }
    }
    asyncio.run(chained_flow(example_payload))
