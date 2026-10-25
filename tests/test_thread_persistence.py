import asyncio

import pytest
from langgraph.types import Command

from tests.postgres_graph import PostgresGraphContext


if __name__ != "__main__":
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.mark.anyio
async def test_thread_persists_across_reconnect():

    thread_id = "test-persistent-thread-001"

    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    initial_state = {
        "messages": [
            {
                "role": "user",
                "content": (
                    "Find me an Italian restaurant in Mayfair "
                    "for 2 people tomorrow at 19:00."
                ),
            }
        ],
        "user_id": "persistent-test-user",
        "thread_id": thread_id,
        "location": "Mayfair",
        "cuisine": "Italian",
        "date": "2026-09-20",
        "time": "19:00",
        "party_size": 2,
        "budget": None,
        "selected_restaurant_id": None,
        "available_restaurants": [],
        "availability_results": [],
        "booking_requested": False,
        "reservation_id": None,
        "reservation_status": None,
        "task_status": "new",
    }

    # ---------------------------------------------------------
    # FIRST CONNECTION
    # ---------------------------------------------------------

    async with PostgresGraphContext() as graph:

        result = await graph.ainvoke(
            initial_state,
            config,
        )

        assert result is not None

        # The graph should either reach an interrupt or
        # complete a checkpoint for this thread.
        snapshot = await graph.aget_state(config)

        assert snapshot is not None
        assert snapshot.config["configurable"]["thread_id"] == thread_id

    # ---------------------------------------------------------
    # SECOND CONNECTION
    # ---------------------------------------------------------

    async with PostgresGraphContext() as graph:

        snapshot = await graph.aget_state(config)

        assert snapshot is not None

        assert (
            snapshot.config["configurable"]["thread_id"]
            == thread_id
        )

        # Verify that state survived closing and reopening
        # the PostgreSQL checkpointer.
        saved_state = snapshot.values

        assert saved_state["thread_id"] == thread_id
        assert saved_state["location"] == "Mayfair"
        assert saved_state["cuisine"] == "Italian"
        assert saved_state["party_size"] == 2