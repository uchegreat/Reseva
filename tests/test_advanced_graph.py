import uuid
import pytest

from langchain_core.messages import HumanMessage

from database.db import SessionLocal
from database.models import User
from database.memory_repository import save_memory

from agent.advanced_graph import builder


@pytest.mark.asyncio
async def test_advanced_graph_loads_memory():
    external_id = (
        f"advanced-memory-test-user-{uuid.uuid4()}"
    )

    thread_id = (
        f"advanced-memory-test-thread-{uuid.uuid4()}"
    )

    db = SessionLocal()

    try:
        user = User(
            external_id=external_id
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        save_memory(
            db=db,
            user_id=user.id,
            memory_type="preference",
            memory_key="preferred_cuisine",
            memory_value="Italian",
        )

    finally:
        db.close()

    graph = builder.compile()

    result = await graph.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content="Find me a restaurant for dinner."
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

    assert (
        result["long_term_memories"]
        ["preferred_cuisine"]
        == "Italian"
    )

    assert (
        result["original_user_request"]
        == "Find me a restaurant for dinner."
    )

    assert result["plan_goal"]

    assert len(
        result["plan_steps"]
    ) > 0

    assert isinstance(
        result["missing_information"],
        list,
    )





