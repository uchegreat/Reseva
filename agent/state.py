from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class ResevaState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    thread_id: str

    location: str | None
    cuisine: str | None
    date: str | None
    time: str | None
    party_size: int | None
    budget: float | None

    selected_restaurant_id: str | None
    available_restaurants: list[dict]
    availability_results: list[dict]

    booking_requested: bool

    reservation_id: str | None
    reservation_status: str | None
    reservation_lookup: dict | None

    email_status: str | None
    email_result: dict | None


    modification_requested: bool
    reservation_id_to_modify: str | None
    modification_date: str | None
    modification_time: str | None
    modification_party_size: int | None

    cancellation_requested: bool

    task_status: str

    # Autonomous agent state
    plan: list[str]
    current_step: str | None
    last_tool: str | None
    last_tool_result: dict | None
    retry_count: int