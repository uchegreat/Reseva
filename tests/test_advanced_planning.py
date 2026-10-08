
import uuid

import pytest
from langchain_core.messages import HumanMessage

from agent.advanced_graph import builder


@pytest.mark.asyncio
async def test_advanced_graph_creates_plan():
    external_id = (
        f"planning-test-user-{uuid.uuid4()}"
    )

    thread_id = (
        f"planning-test-thread-{uuid.uuid4()}"
    )

    graph = builder.compile()

    result = await graph.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "Find me an Italian restaurant in Mayfair "
                        "for 4 people tomorrow at 7pm."
                    )
                )
            ],
            "user_id": external_id,
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
            "task_status": "processing",

            "long_term_memories": {},
            "original_user_request": None,

            "plan_goal": None,
            "plan_steps": [],
            "missing_information": [],
        }
    )

    assert result["plan_goal"]

    assert isinstance(
        result["plan_steps"],
        list,
    )

    assert len(
        result["plan_steps"]
    ) > 0

    assert isinstance(
        result["missing_information"],
        list,
    )



