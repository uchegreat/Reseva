import asyncio
import uuid

import pytest

from langgraph.types import Command

from api.graph_runtime import ResevaGraphRuntime


if __name__ != "__main__":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )


@pytest.mark.anyio
async def test_api_runtime_booking_interrupt():
    thread_id = (
        f"api-chat-test-{uuid.uuid4()}"
    )

    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    async with ResevaGraphRuntime() as graph:
        result = await graph.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Book an Italian restaurant "
                            "in Mayfair tomorrow at 19:00 "
                            "for 2 people."
                        ),
                    }
                ],
                "user_id": "api-test-user",
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

        print("\n--- GRAPH RESULT ---")
        print(result)
        print("\n--- INTERRUPT DATA ---")
        print(result.get("__interrupt__"))

        assert result is not None
        assert "__interrupt__" in result
        assert result["__interrupt__"]