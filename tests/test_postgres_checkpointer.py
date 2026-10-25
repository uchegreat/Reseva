import asyncio

import pytest

from tests.postgres_graph import PostgresGraphContext


if __name__ != "__main__":
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.mark.anyio
async def test_postgres_checkpointer():
    thread_id = "test-postgres-checkpointer-001"

    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    async with PostgresGraphContext() as graph:
        result = await graph.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Hello Reseva",
                    }
                ],
                "user_id": "test-user",
                "thread_id": thread_id,
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
                "task_status": "new",
            },
            config,
        )

        assert result is not None