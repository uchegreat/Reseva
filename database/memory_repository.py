from sqlalchemy.orm import Session

from database.models import UserMemory


def save_memory(
    db: Session,
    user_id: int,
    memory_type: str,
    memory_key: str,
    memory_value: str,
) -> UserMemory:
    """
    Create or update a user's long-term memory.

    A user can only have one memory for a given
    memory_type + memory_key combination.
    """

    existing_memory = (
        db.query(UserMemory)
        .filter(
            UserMemory.user_id == user_id,
            UserMemory.memory_type == memory_type,
            UserMemory.memory_key == memory_key,
        )
        .first()
    )

    if existing_memory:
        existing_memory.memory_value = memory_value

        db.commit()
        db.refresh(existing_memory)

        return existing_memory

    memory = UserMemory(
        user_id=user_id,
        memory_type=memory_type,
        memory_key=memory_key,
        memory_value=memory_value,
    )

    db.add(memory)

    db.commit()
    db.refresh(memory)

    return memory


def get_user_memories(
    db: Session,
    user_id: int,
) -> list[UserMemory]:
    """
    Return all long-term memories belonging to a user.
    """

    return (
        db.query(UserMemory)
        .filter(UserMemory.user_id == user_id)
        .order_by(UserMemory.updated_at.desc())
        .all()
    )


def get_memory(
    db: Session,
    user_id: int,
    memory_type: str,
    memory_key: str,
) -> UserMemory | None:
    """
    Retrieve one specific memory.
    """

    return (
        db.query(UserMemory)
        .filter(
            UserMemory.user_id == user_id,
            UserMemory.memory_type == memory_type,
            UserMemory.memory_key == memory_key,
        )
        .first()
    )


def delete_memory(
    db: Session,
    user_id: int,
    memory_type: str,
    memory_key: str,
) -> bool:
    """
    Delete one specific memory.

    Returns True if a memory was deleted.
    """

    memory = get_memory(
        db,
        user_id,
        memory_type,
        memory_key,
    )

    if not memory:
        return False

    db.delete(memory)
    db.commit()

    return True
def get_user_memory_context(
    db: Session,
    user_id: int,
) -> dict[str, str]:
    """
    Return a user's memories as a simple dictionary
    that can be provided to the AI agent.
    """

    memories = get_user_memories(
        db=db,
        user_id=user_id,
    )

    return {
        memory.memory_key: memory.memory_value
        for memory in memories
    }