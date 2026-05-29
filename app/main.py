# ══════════════════════════════════════════════════════════════════════════
#  A2A Agent Server — Main entry point
#  Serves: A2A protocol endpoints + Agent Card (ORD) + optional web UI
# ══════════════════════════════════════════════════════════════════════════

import os
import json
import logging
import argparse
import uuid
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from .agent_executor import execute_agent

# ── Config ──────────────────────────────────────────────────────────────

AGENT_NAME = "onboarding_assignment_agent"
AGENT_DESCRIPTION = (
    "MILP-optimized consultant-to-customer assignment agent. "
    "Loads consultant data, analyzes capacity across regions (APJ, MEE, EMEA, GC, LAC, NA), "
    "looks up individual consultants, ranks performers, and runs Mixed Integer Linear Programming "
    "optimization to fairly assign customers to consultants based on bandwidth, willingness, "
    "experience, feedback, and attendance scores."
)
AGENT_TAGS = ["onboarding", "assignment", "milp", "optimization", "consultant", "capacity"]
AGENT_EXAMPLES = [
    "Show me the regional capacity overview",
    "Look up consultant John Smith",
    "Who are the top 5 consultants?",
    "Run assignment for these customers: {\"APJ\": [\"C001\", \"C002\"], \"NA\": [\"C003\"]}",
    "How does the scoring methodology work?",
]

PORT = int(os.getenv("PORT", "5000"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── App ─────────────────────────────────────────────────────────────────

app = FastAPI(title="Onboarding Assignment A2A Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Agent Card (ORD/A2A Discovery) ─────────────────────────────────────

AGENT_CARD = {
    "name": AGENT_NAME,
    "description": AGENT_DESCRIPTION,
    "url": f"http://localhost:{PORT}",
    "version": "1.0.0",
    "capabilities": {
        "streaming": False,
        "pushNotifications": False,
    },
    "skills": [
        {
            "id": "load_data",
            "name": "Load Consultant Data",
            "description": "Load and process consultant Excel/CSV data for analysis and assignment",
        },
        {
            "id": "capacity",
            "name": "Regional Capacity",
            "description": "Show capacity overview across all regions",
        },
        {
            "id": "lookup",
            "name": "Consultant Lookup",
            "description": "Look up a consultant by name with full metrics",
        },
        {
            "id": "top_performers",
            "name": "Top Performers",
            "description": "Rank consultants by score",
        },
        {
            "id": "assign",
            "name": "Run MILP Assignment",
            "description": "Optimize customer-to-consultant assignment using MILP solver",
        },
        {
            "id": "scoring",
            "name": "Explain Scoring",
            "description": "Explain the scoring methodology and weights",
        },
    ],
    "tags": AGENT_TAGS,
    "examples": AGENT_EXAMPLES,
}


@app.get("/agent-card")
@app.get("/.well-known/agent.json")
async def get_agent_card():
    """A2A Agent Card endpoint for discovery."""
    return JSONResponse(content=AGENT_CARD)


# ── A2A Task Endpoints ──────────────────────────────────────────────────

class TaskRequest(BaseModel):
    id: Optional[str] = None
    message: dict  # {"role": "user", "parts": [{"type": "text", "text": "..."}]}
    sessionId: Optional[str] = None


class TaskResponse(BaseModel):
    id: str
    sessionId: str
    status: dict
    artifacts: Optional[list] = None


@app.post("/tasks/send")
async def send_task(request: TaskRequest):
    """A2A send task — synchronous execution."""
    task_id = request.id or str(uuid.uuid4())
    session_id = request.sessionId or str(uuid.uuid4())

    # Extract user message text
    user_text = ""
    if request.message and "parts" in request.message:
        for part in request.message["parts"]:
            if part.get("type") == "text":
                user_text += part.get("text", "")
    elif request.message and "content" in request.message:
        user_text = request.message["content"]

    if not user_text:
        raise HTTPException(status_code=400, detail="No text message provided")

    logger.info(f"Task {task_id}: Processing message: {user_text[:100]}...")

    # Execute agent
    final_content = ""
    async for event in execute_agent(user_text, session_id):
        if event["type"] == "message":
            final_content = event["content"]

    return TaskResponse(
        id=task_id,
        sessionId=session_id,
        status={"state": "completed"},
        artifacts=[
            {
                "parts": [{"type": "text", "text": final_content}]
            }
        ],
    )


# ── Health ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "agent": AGENT_NAME}


# ── Web UI Chat API (bridges frontend to agent) ───────────────────────

from fastapi import UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path
import io
import pandas as pd

from .tools import store
from .engine import clean_dataframe, calculate_scores

FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "out"


class ChatRequest(BaseModel):
    message: str
    customer_data: Optional[str] = None
    cross_region_pcts: Optional[dict] = None
    history: Optional[list] = None


@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    """Web UI chat endpoint — routes through the agent."""
    user_text = req.message
    if req.customer_data and any(k in user_text.lower() for k in ['assign', 'run', 'optimize']):
        user_text += f"\n\nCustomer data JSON: {req.customer_data}"
        if req.cross_region_pcts and any(v > 0 for v in req.cross_region_pcts.values()):
            user_text += f"\n\nCross-region percentages (redirect to APJ): {req.cross_region_pcts}"

    final_content = ""
    async for event in execute_agent(user_text, "web-ui"):
        if event["type"] == "message":
            final_content = event["content"]

    return {"response": final_content}


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    """Upload consultant Excel/CSV via web UI."""
    try:
        contents = await file.read()
        filename = file.filename or "data.xlsx"
        if filename.endswith('.csv'):
            raw_df = pd.read_csv(io.BytesIO(contents), keep_default_na=False)
        else:
            raw_df = pd.read_excel(io.BytesIO(contents), keep_default_na=False)

        df = clean_dataframe(raw_df)
        df_scored, weights = calculate_scores(df)
        store.df = df
        store.df_scored = df_scored
        store.weights = weights

        active = df_scored[df_scored['Is_Available'] == 1]
        return {
            "file_name": filename,
            "row_count": len(df_scored),
            "active_count": len(active),
            "total_capacity": int(active['Can_Take'].sum()),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process file: {str(e)}")


# ── Static Frontend Serving ────────────────────────────────────────────

if FRONTEND_DIR.exists():
    next_static = FRONTEND_DIR / "_next"
    if next_static.exists():
        app.mount("/_next", StaticFiles(directory=str(next_static)), name="next-static")

    @app.get("/{full_path:path}")
    async def serve_frontend(request: Request, full_path: str):
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        index = FRONTEND_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return HTMLResponse("<h1>Frontend not built</h1>", status_code=404)
else:
    @app.get("/")
    async def root():
        return HTMLResponse(
            "<h1>Onboarding Assignment Agent (A2A)</h1>"
            "<p>Frontend not built. Run: cd frontend && npm install && npm run build</p>"
            "<p><a href='/agent-card'>Agent Card</a> | <a href='/health'>Health</a></p>"
        )


# ── Main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Onboarding Assignment A2A Agent")
    parser.add_argument("--port", type=int, default=PORT, help="Server port")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Server host")
    args = parser.parse_args()

    print("=" * 60)
    print("  Onboarding Assignment Agent (A2A Protocol)")
    print("=" * 60)
    print(f"  Server:      http://localhost:{args.port}")
    print(f"  Agent Card:  http://localhost:{args.port}/agent-card")
    print(f"  Health:      http://localhost:{args.port}/health")
    print(f"  A2A Tasks:   POST http://localhost:{args.port}/tasks/send")
    print(f"  Model:       {os.getenv('AICORE_MODEL', 'not set')}")
    print("=" * 60)

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
