from fastapi import FastAPI, HTTPException
from prefect.client.orchestration import get_client
from pydantic import BaseModel
from typing import Dict

app = FastAPI()

class AnalysisRequest(BaseModel):
    query_criteria: Dict

@app.post("/analyze")
async def trigger_analysis(request: AnalysisRequest):
    """API endpoint to trigger analysis workflow"""
    try:
        async with get_client() as client:
            flow_run = await client.create_flow_run(
                flow_name="main_orchestrator",
                parameters={"payload": request.dict()},
                work_pool_name="orchestrator-pool"
            )
        return {"flow_run_id": str(flow_run.id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)