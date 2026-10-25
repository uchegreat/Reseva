import asyncio
import uuid

import pytest

from tests.postgres_graph import PSYCOPG_DATABASE_URL
from agent.advanced_graph import compile_advanced_graph
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


if __name__ != "__main__":
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.mark.anyio
async def test_advanced_graph_with_postgres_checkpointer():
    thread_id = (
        f"advanced-postgres-test-{uuid.uuid4()}"
    )

    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    async with AsyncPostgresSaver.from_conn_string(
        PSYCOPG_DATABASE_URL
    ) as checkpointer:

        graph = compile_advanced_graph(
            checkpointer
        )

        result = await graph.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Find me an Italian restaurant in Mayfair.",
                    }
                ],
                "user_id": "advanced-postgres-test-user",
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

        assert result is not None