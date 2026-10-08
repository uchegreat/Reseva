
import uuid
import pytest

from langchain_core.messages import HumanMessage

from agent.advanced_graph import builder
from database.db import SessionLocal
from database.models import User
from database.memory_repository import get_memory


@pytest.mark.asyncio
async def test_advanced_graph_learns_user_preference():
    external_id = f"memory-learning-user-{uuid.uuid4()}"
    thread_id = f"memory-learning-thread-{uuid.uuid4()}"

    db = SessionLocal()

    try:
        user = User(
            external_id=external_id
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        user_id = user.id

    finally:
        db.close()

    graph = builder.compile()

    await graph.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content="I prefer Italian restaurants."
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

    db = SessionLocal()

    try:
        memory = get_memory(
            db=db,
            user_id=user_id,
            memory_type="preference",
            memory_key="preferred_cuisine",
        )

        assert memory is not None
        assert memory.memory_value == "Italian"

    finally:
        db.close()




