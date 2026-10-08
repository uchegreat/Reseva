import asyncio

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from agent.state import ResevaState
import agent.graph as graph_module


class FakeTool:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def ainvoke(self, payload):
        self.calls.append(payload)
        return self.result


def base_state(**overrides):
    state = {
        "messages": [HumanMessage(content="Change my reservation")],
        "user_id": "test-user",
        "thread_id": "test-modification",
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
        "reservation_id": "res-test-modify-graph-001",
        "reservation_status": "confirmed",
        "reservation_lookup": None,
        "modification_requested": True,
        "reservation_id_to_modify": "res-test-modify-graph-001",
        "modification_date": "2026-09-26",
        "modification_time": "20:00",
        "modification_party_size": 3,
        "cancellation_requested": False,
        "task_status": "processing",
    }
    state.update(overrides)
    return state


def test_modification_routes_before_normal_booking():
    state = base_state(modification_requested=True, cancellation_requested=False)
    assert graph_module.route_after_extract_state(state) == "modification_lookup"


def test_modification_lookup_and_availability(monkeypatch):
    lookup_tool = FakeTool({
        "success": True,
        "reservation": {
            "reservation_id": "res-test-modify-graph-001",
            "restaurant_id": "rest-001",
            "restaurant_name": "Bella Italia Mayfair",
            "date": "2026-09-25",
            "time": "19:00",
            "party_size": 2,
            "status": "confirmed",
        },
    })
    availability_tool = FakeTool({
        "success": True,
        "available": True,
        "restaurant_id": "rest-001",
        "date": "2026-09-26",
        "time": "20:00",
        "party_size": 3,
    })

    monkeypatch.setattr(graph_module, "get_reservation", lookup_tool)
    monkeypatch.setattr(graph_module, "check_availability", availability_tool)

    state = base_state()
    looked_up = asyncio.run(graph_module.modification_lookup_node(state))

    merged = dict(state)
    merged.update(looked_up)

    assert looked_up["task_status"] == "modification_checking_availability"
    assert looked_up["modification_date"] == "2026-09-26"
    assert looked_up["modification_time"] == "20:00"
    assert looked_up["modification_party_size"] == 3

    checked = asyncio.run(graph_module.modification_availability_node(merged))

    assert checked["task_status"] == "modification_ready"
    assert availability_tool.calls == [{
        "restaurant_id": "rest-001",
        "date": "2026-09-26",
        "time": "20:00",
        "party_size": 3,
    }]


def test_modification_unavailable_does_not_become_ready(monkeypatch):
    availability_tool = FakeTool({
        "success": True,
        "available": False,
        "restaurant_id": "rest-001",
        "date": "2026-09-26",
        "time": "20:00",
        "party_size": 3,
    })
    monkeypatch.setattr(graph_module, "check_availability", availability_tool)

    state = base_state(
        reservation_lookup={
            "reservation_id": "res-test-modify-graph-001",
            "restaurant_id": "rest-001",
            "restaurant_name": "Bella Italia Mayfair",
            "date": "2026-09-25",
            "time": "19:00",
            "party_size": 2,
            "status": "confirmed",
        }
    )

    result = asyncio.run(graph_module.modification_availability_node(state))

    assert result["task_status"] == "modification_unavailable"


def test_modification_approval_pauses_and_resumes():
    builder = StateGraph(ResevaState)
    builder.add_node("approval", graph_module.modification_approval)
    builder.add_edge(START, "approval")
    builder.add_edge("approval", END)
    compiled = builder.compile(checkpointer=InMemorySaver())

    config = {"configurable": {"thread_id": "modify-approval-test-001"}}
    state = base_state(
        reservation_lookup={
            "reservation_id": "res-test-modify-graph-001",
            "restaurant_id": "rest-001",
            "restaurant_name": "Bella Italia Mayfair",
            "date": "2026-09-25",
            "time": "19:00",
            "party_size": 2,
            "status": "confirmed",
        }
    )

    asyncio.run(compiled.ainvoke(state, config=config))
    snapshot = compiled.get_state(config)

    assert snapshot.interrupts
    interrupt_value = snapshot.interrupts[0].value
    assert interrupt_value["type"] == "modification_confirmation"
    assert interrupt_value["old_time"] == "19:00"
    assert interrupt_value["new_time"] == "20:00"

    asyncio.run(compiled.ainvoke(Command(resume="yes"), config=config))
    final_state = compiled.get_state(config).values

    assert final_state["task_status"] == "modification_approved"


def test_modify_node_only_calls_tool_with_new_values(monkeypatch):
    modify_tool = FakeTool({
        "success": True,
        "reservation": {
            "reservation_id": "res-test-modify-graph-001",
            "restaurant_id": "rest-001",
            "restaurant_name": "Bella Italia Mayfair",
            "date": "2026-09-26",
            "time": "20:00",
            "party_size": 3,
            "status": "confirmed",
        },
    })
    monkeypatch.setattr(graph_module, "modify_reservation", modify_tool)

    result = asyncio.run(
        graph_module.modify_reservation_node(base_state())
    )

    assert result["task_status"] == "completed"
    assert result["reservation_status"] == "confirmed"
    assert result["date"] == "2026-09-26"
    assert result["time"] == "20:00"
    assert result["party_size"] == 3
    assert modify_tool.calls == [{
        "reservation_id": "res-test-modify-graph-001",
        "date": "2026-09-26",
        "time": "20:00",
        "party_size": 3,
    }]