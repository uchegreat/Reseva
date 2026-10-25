import os
import time
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langgraph_sdk import get_client

from api.schemas import ChatRequest, ChatResponse, ResumeRequest

load_dotenv()

# ---------------------------------------------------------
# MODE
# ---------------------------------------------------------
# Inside the LangSmith deployment (RESEVA_IN_PROCESS=1) this app runs in
# the same server as the agent, so it calls the agent directly.
# On your laptop it keeps using LANGGRAPH_API_URL + LANGSMITH_API_KEY.

RUN_IN_PROCESS = os.getenv("RESEVA_IN_PROCESS", "").strip().lower() in {
    "1",
    "true",
    "yes",
}

LANGGRAPH_API_URL = os.getenv("LANGGRAPH_API_URL")
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
ASSISTANT_ID = "63862a13-3951-5b6e-9382-a4a260a060ee"

if not RUN_IN_PROCESS and (not LANGGRAPH_API_URL or not LANGSMITH_API_KEY):
    raise RuntimeError(
        "LANGGRAPH_API_URL and LANGSMITH_API_KEY must be configured in .env"
    )

_client = None


def get_langgraph_client():
    """Create the LangGraph client on first use (not at import time)."""

    global _client

    if _client is None:
        if RUN_IN_PROCESS:
            _client = get_client()
        else:
            _client = get_client(
                url=LANGGRAPH_API_URL,
                api_key=LANGSMITH_API_KEY,
            )

    return _client


app = FastAPI(
    title="Reseva API",
    description="AI-powered restaurant reservation API",
    version="1.0.0",
)

# ---------------------------------------------------------
# CORS (local development only)
# ---------------------------------------------------------
# In the deployment the web app and this API share one address, so CORS
# is not needed there. Locally the Vite dev server runs on another port.

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

if not RUN_IN_PROCESS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# ---------------------------------------------------------
# SIMPLE RATE LIMIT (per visitor, in memory)
# ---------------------------------------------------------
# Protects your Anthropic credits from runaway or abusive traffic.
# Best effort: the deployment runs one replica, so memory is enough.

RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))
_recent_requests: dict[str, deque] = defaultdict(deque)


def enforce_rate_limit(request: Request) -> None:
    forwarded = request.headers.get("x-forwarded-for", "")

    if forwarded:
        visitor = forwarded.split(",")[0].strip()
    elif request.client:
        visitor = request.client.host
    else:
        visitor = "unknown"

    now = time.monotonic()
    window = _recent_requests[visitor]

    while window and now - window[0] > 60:
        window.popleft()

    if len(window) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait a moment and try again.",
        )

    window.append(now)


# ---------------------------------------------------------
# ROUTES
# ---------------------------------------------------------


@app.get("/api/v1/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "reseva-api",
        "version": "1.0.0",
    }


def build_response(thread_id: str, result) -> ChatResponse:
    """Convert a hosted LangGraph result into the existing API response."""

    if isinstance(result, list):
        result = result[-1] if result else {}

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=502,
            detail="Unexpected response from the hosted LangGraph deployment.",
        )

    interrupts = result.get("__interrupt__", [])

    if interrupts:
        interrupt = interrupts[0]
        interrupt_data = getattr(interrupt, "value", interrupt)

        if not isinstance(interrupt_data, dict):
            interrupt_data = {"message": str(interrupt_data)}

        return ChatResponse(
            thread_id=thread_id,
            status="approval_required",
            message=interrupt_data.get(
                "message",
                "Your approval is required.",
            ),
            data={"__interrupt__": [interrupt_data]},
        )

    return ChatResponse(
        thread_id=thread_id,
        status=result.get("task_status", "completed"),
        message="Request processed successfully.",
        data=result,
    )


@app.post(
    "/api/v1/chat",
    response_model=ChatResponse,
)
async def chat(chat_request: ChatRequest, request: Request):
    enforce_rate_limit(request)

    try:
        result = await get_langgraph_client().runs.wait(
            thread_id=chat_request.thread_id,
            assistant_id=ASSISTANT_ID,
            input={
                "messages": [
                    {
                        "type": "human",
                        "content": chat_request.message,
                    }
                ],
            },
            config={
                "configurable": {
                    "user_id": chat_request.user_id,
                    "thread_id": chat_request.thread_id,
                }
            },
            if_not_exists="create",
        )

        return build_response(chat_request.thread_id, result)

    except HTTPException:
        raise
    except Exception as exc:
        # Keep internal exception details out of the API response.
        print(f"Hosted LangGraph chat error: {exc}")
        raise HTTPException(
            status_code=502,
            detail="The hosted reservation service could not process the request.",
        ) from exc


@app.post(
    "/api/v1/chat/{thread_id}/resume",
    response_model=ChatResponse,
)
async def resume_chat(
    thread_id: str,
    resume_request: ResumeRequest,
    request: Request,
):
    enforce_rate_limit(request)

    try:
        result = await get_langgraph_client().runs.wait(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID,
            command={
                "resume": resume_request.approval,
            },
        )

        return build_response(thread_id, result)

    except HTTPException:
        raise
    except Exception as exc:
        print(f"Hosted LangGraph resume error: {exc}")
        raise HTTPException(
            status_code=502,
            detail="The hosted reservation service could not resume the request.",
        ) from exc


# ---------------------------------------------------------
# FRONTEND (built React app, served at /app/)
# ---------------------------------------------------------
# Build the frontend and copy it into the static_app folder at the project
# root. If the folder is missing, the API still works without the web app.

STATIC_DIR = Path(__file__).resolve().parent.parent / "static_app"

if STATIC_DIR.is_dir():
    app.mount(
        "/app",
        StaticFiles(directory=STATIC_DIR, html=True),
        name="reseva-frontend",
    )