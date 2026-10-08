import asyncio

import pytest
from langgraph.types import Command

from tests.postgres_graph import PostgresGraphContext


if __name__ != "__main__":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )


@pytest.mark.anyio
async def test_booking_resumes_after_reconnect():

    thread_id = "test-booking-resume-001"

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
                    "Book Bella Italia Mayfair for 2 people "
                    "tomorrow at 19:00."
                ),
            }
        ],
        "user_id": "resume-test-user",
        "thread_id": thread_id,
        "location": "Mayfair",
        "cuisine": "Italian",
        "date": "2026-09-20",
        "time": "19:00",
        "party_size": 2,
        "budget": None,
        "selected_restaurant_id": "rest-001",
        "available_restaurants": [],
        "availability_results": [],
        "booking_requested": True,
        "reservation_id": None,
        "reservation_status": None,
        "task_status": "new",
    }

    # =========================================================
    # CONNECTION 1
    # Start the booking and reach the approval interrupt.
    # =========================================================

    async with PostgresGraphContext() as graph:

        result = await graph.ainvoke(
            initial_state,
            config,
        )

        assert result is not None

        snapshot = await graph.aget_state(config)

        assert snapshot is not None

        # The graph should be interrupted waiting for approval.
        assert snapshot.next

        # Verify the thread has been persisted.
        assert (
            snapshot.config["configurable"]["thread_id"]
            == thread_id
        )

    # =========================================================
    # CONNECTION 2
    # Reconnect using the SAME thread ID.
    # =========================================================

    async with PostgresGraphContext() as graph:

        snapshot = await graph.aget_state(config)

        assert snapshot is not None

        assert (
            snapshot.config["configurable"]["thread_id"]
            == thread_id
        )

        # Confirm that the booking state survived the reconnect.
        assert snapshot.values["thread_id"] == thread_id
        assert snapshot.values["selected_restaurant_id"] == "rest-001"
        assert snapshot.values["booking_requested"] is True

        # =====================================================
        # Resume the interrupted workflow.
        # =====================================================

        result = await graph.ainvoke(
            Command(resume="yes"),
            config,
        )

        assert result is not None

        # =====================================================
        # Verify that the reservation completed.
        # =====================================================

        final_state = await graph.aget_state(config)

        assert final_state is not None

        assert (
            final_state.values["reservation_status"]
            == "confirmed"
        )

        assert final_state.values["reservation_id"] is not None