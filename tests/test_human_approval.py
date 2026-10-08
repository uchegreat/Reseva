import asyncio

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )

import asyncio
import os
import uuid

import pytest
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from agent.graph import build_graph, builder


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set.")

PSYCOPG_DATABASE_URL = DATABASE_URL.replace(
    "postgresql+psycopg://",
    "postgresql://",
)


@pytest.mark.asyncio
async def test_human_approval_pauses_and_resumes():
    thread_id = f"human-approval-{uuid.uuid4()}"

    async with AsyncPostgresSaver.from_conn_string(
        PSYCOPG_DATABASE_URL
    ) as checkpointer:

        graph = build_graph(checkpointer)

        initial_state = {
            "messages": [
                HumanMessage(
                    content=(
                        "Book Bella Italia Mayfair for 2 people "
                        "on 2026-09-25 at 19:00."
                    )
                )
            ],
            "user_id": "test-user",
            "thread_id": thread_id,
            "location": "Mayfair",
            "cuisine": "Italian",
            "date": "2026-09-25",
            "time": "19:00",
            "party_size": 2,
            "budget": None,
            "selected_restaurant_id": "rest-001",
            "available_restaurants": [
                {
                    "id": "rest-001",
                    "name": "Bella Italia Mayfair",
                    "location": "Mayfair",
                    "cuisine": "Italian",
                }
            ],
            "availability_results": [
                {
                    "available": True,
                    "restaurant_id": "rest-001",
                    "date": "2026-09-25",
                    "time": "19:00",
                    "party_size": 2,
                }
            ],
            "booking_requested": True,
            "reservation_id": None,
            "reservation_status": None,
            "task_status": "processing",
        }

        config = {
            "configurable": {
                "thread_id": thread_id,
            }
        }

        # First execution should pause at human approval.
        result = await graph.ainvoke(
            initial_state,
            config=config,
        )

        assert "__interrupt__" in result
        assert result["__interrupt__"]

        # Confirm the graph is waiting for approval.
        interrupt_value = result["__interrupt__"][0].value

        assert interrupt_value["type"] == "booking_confirmation"
        assert interrupt_value["restaurant_id"] == "rest-001"
        assert interrupt_value["date"] == "2026-09-25"
        assert interrupt_value["time"] == "19:00"
        assert interrupt_value["party_size"] == 2

        # The reservation must NOT exist yet.
        snapshot = await graph.aget_state(config)

        assert snapshot.values["reservation_id"] is None
        assert snapshot.values["reservation_status"] is None

        # Resume the SAME thread with explicit approval.
        result = await graph.ainvoke(
            Command(resume="yes"),
            config=config,
        )

        # Reservation should now be created.
        assert result["reservation_id"]
        assert result["reservation_id"].startswith("res-")
        assert result["reservation_status"] == "confirmed"
        assert result["task_status"] == "completed"

@pytest.mark.asyncio
async def test_human_approval_rejection_does_not_create_reservation():
    thread_id = f"human-rejection-{uuid.uuid4()}"

    async with AsyncPostgresSaver.from_conn_string(
        PSYCOPG_DATABASE_URL
    ) as checkpointer:

        graph = build_graph(checkpointer)

        initial_state = {
            "messages": [
                HumanMessage(
                    content=(
                        "Book Bella Italia Mayfair for 2 people "
                        "on 2026-09-25 at 19:00."
                    )
                )
            ],
            "user_id": "test-user",
            "thread_id": thread_id,
            "location": "Mayfair",
            "cuisine": "Italian",
            "date": "2026-09-25",
            "time": "19:00",
            "party_size": 2,
            "budget": None,
            "selected_restaurant_id": "rest-001",
            "available_restaurants": [
                {
                    "id": "rest-001",
                    "name": "Bella Italia Mayfair",
                    "location": "Mayfair",
                    "cuisine": "Italian",
                }
            ],
            "availability_results": [
                {
                    "available": True,
                    "restaurant_id": "rest-001",
                    "date": "2026-09-25",
                    "time": "19:00",
                    "party_size": 2,
                }
            ],
            "booking_requested": True,
            "reservation_id": None,
            "reservation_status": None,
            "task_status": "processing",
        }

        config = {
            "configurable": {
                "thread_id": thread_id,
            }
        }

        # First execution pauses for approval.
        result = await graph.ainvoke(
            initial_state,
            config=config,
        )

        assert "__interrupt__" in result
        assert result["__interrupt__"]

        # Reject the booking.
        result = await graph.ainvoke(
            Command(resume="no"),
            config=config,
        )

        # A rejected booking must never be created.
        assert result["reservation_id"] is None
        assert result["reservation_status"] is None
        assert result["task_status"] != "completed"