import uuid

from database.db import SessionLocal
from database.memory_repository import (
    save_memory,
    get_user_memories,
    get_memory,
    delete_memory,
)


def test_memory_repository():
    db = SessionLocal()

    try:
        from database.models import User

        user = User(
            external_id=f"memory-test-user-{uuid.uuid4()}"
        )

        db.add(user)
        db.commit()
        db.refresh(user)
        
        # Save memory
        memory = save_memory(
            db=db,
            user_id=user.id,
            memory_type="preference",
            memory_key="preferred_cuisine",
            memory_value="Italian",
        )

        assert memory.memory_value == "Italian"

        # Retrieve memory
        retrieved = get_memory(
            db=db,
            user_id=user.id,
            memory_type="preference",
            memory_key="preferred_cuisine",
        )

        assert retrieved is not None
        assert retrieved.memory_value == "Italian"

        # Update memory
        updated = save_memory(
            db=db,
            user_id=user.id,
            memory_type="preference",
            memory_key="preferred_cuisine",
            memory_value="Japanese",
        )

        assert updated.memory_value == "Japanese"

        # Make sure we didn't create a duplicate
        memories = get_user_memories(
            db=db,
            user_id=user.id,
        )

        assert len(memories) == 1

        # Delete memory
        deleted = delete_memory(
            db=db,
            user_id=user.id,
            memory_type="preference",
            memory_key="preferred_cuisine",
        )

        assert deleted is True

        # Confirm deletion
        retrieved_after_delete = get_memory(
            db=db,
            user_id=user.id,
            memory_type="preference",
            memory_key="preferred_cuisine",
        )

        assert retrieved_after_delete is None

    finally:
        db.close()