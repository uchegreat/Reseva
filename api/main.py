from fastapi import FastAPI, HTTPException
from langgraph.types import Command

from api.graph_runtime import ResevaGraphRuntime
from api.schemas import (
    ChatRequest,
    ChatResponse,
    ResumeRequest,
)


app = FastAPI(
    title="Reseva API",
    description="AI-powered restaurant reservation API",
    version="1.0.0",
)


@app.get("/api/v1/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "reseva-api",
        "version": "1.0.0",
    }


@app.post(
    "/api/v1/chat",
    response_model=ChatResponse,
)
async def chat(request: ChatRequest):
    config = {
        "configurable": {
            "thread_id": request.thread_id,
        }
    }

    try:
        async with ResevaGraphRuntime() as graph:
            result = await graph.ainvoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": request.message,
                        }
                    ],
                    "user_id": request.user_id,
                    "thread_id": request.thread_id,

                    "location": None,
                    "cuisine": None,
                    "date": None,
                    "time": None,
                    "party_size": None,
                    "budget": None,

                    "selected_restaurant_id": None,
                    "available_restaurants": [],
                    "availability_results": [],

                    "booking_requested": False,

                    "reservation_id": None,
                    "reservation_status": None,
                    "reservation_lookup": None,

                    "modification_requested": False,
                    "reservation_id_to_modify": None,
                    "modification_date": None,
                    "modification_time": None,
                    "modification_party_size": None,

                    "cancellation_requested": False,

                    "task_status": "new",

                    "plan": [],
                    "current_step": None,
                    "last_tool": None,
                    "last_tool_result": None,
                    "retry_count": 0,

                    "long_term_memories": {},
                    "original_user_request": None,
                    "plan_goal": None,
                    "plan_steps": [],
                    "missing_information": [],

                    "execution_summary": None,
                    "goal_satisfied": False,
                    "adaptation_needed": False,
                    "next_action": None,
                    "adaptation_count": 0,
                },
                config=config,
            )

        interrupts = result.get("__interrupt__", [])

        if interrupts:
            interrupt_data = interrupts[0].value

            return ChatResponse(
                thread_id=request.thread_id,
                status="approval_required",
                message=interrupt_data.get(
                    "message",
                    "Your approval is required.",
                ),
                data=interrupt_data,
            )

        return ChatResponse(
            thread_id=request.thread_id,
            status=result.get(
                "task_status",
                "completed",
            ),
            message="Request processed successfully.",
            data=None,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.post(
    "/api/v1/chat/{thread_id}/resume",
    response_model=ChatResponse,
)
async def resume_chat(
    thread_id: str,
    request: ResumeRequest,
):
    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    try:
        async with ResevaGraphRuntime() as graph:
            result = await graph.ainvoke(
                Command(
                    resume=request.approval
                ),
                config=config,
            )

        interrupts = result.get("__interrupt__", [])

        if interrupts:
            interrupt_data = interrupts[0].value

            return ChatResponse(
                thread_id=thread_id,
                status="approval_required",
                message=interrupt_data.get(
                    "message",
                    "Your approval is required.",
                ),
                data=interrupt_data,
            )

        return ChatResponse(
            thread_id=thread_id,
            status=result.get(
                "task_status",
                "completed",
            ),
            message="Request processed successfully.",
            data=None,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )