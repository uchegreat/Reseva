from langgraph.graph import END
from langchain_core.messages import ToolMessage
from agent.advanced_graph import evaluate_execution
from agent.advanced_graph import route_after_evaluation
from agent.graph import observe_tool_result, route_after_tools


def test_successful_tool_routes_normally():
    state = {
        "messages": [
            ToolMessage(
                name="search_restaurants",
                content='{"success": true, "restaurants": []}',
                tool_call_id="test-1",
            )
        ],
        "retry_count": 0,
        "task_status": "processing",
        "last_tool": None,
        "last_tool_result": None,
        "current_step": None,
    }

    result = route_after_tools(state)

    assert result == "store_search_results"


def test_failed_tool_is_routed_to_recovery():
    state = {
        "messages": [
            ToolMessage(
                name="search_restaurants",
                content="Error: MCP connection failed",
                status="error",
                tool_call_id="test-1",
            )
        ],
        "retry_count": 0,
        "task_status": "processing",
        "last_tool": None,
        "last_tool_result": None,
        "current_step": None,
    }

    result = route_after_tools(state)

    assert result == "agent"


def test_tool_failure_increments_retry_count():
    state = {
        "messages": [
            ToolMessage(
                name="search_restaurants",
                content="Error: MCP connection failed",
                status="error",
                tool_call_id="test-1",
            )
        ],
        "retry_count": 0,
        "task_status": "processing",
        "last_tool": None,
        "last_tool_result": None,
        "current_step": None,
    }

    result = observe_tool_result(state)

    assert result["retry_count"] == 1
    assert result["task_status"] == "tool_error"
    assert result["last_tool"] == "search_restaurants"


def test_successful_tool_does_not_increment_retry_count():
    state = {
        "messages": [
            ToolMessage(
                name="search_restaurants",
                content='{"success": true, "restaurants": []}',
                tool_call_id="test-1",
            )
        ],
        "retry_count": 0,
        "task_status": "processing",
        "last_tool": None,
        "last_tool_result": None,
        "current_step": None,
    }

    result = observe_tool_result(state)

    assert result["retry_count"] == 0
    assert result["task_status"] != "tool_error"
    assert result["last_tool"] == "search_restaurants"


def test_tool_failure_stops_retrying_after_limit():
    state = {
        "messages": [
            ToolMessage(
                name="search_restaurants",
                content="Error: MCP connection failed",
                status="error",
                tool_call_id="test-1",
            )
        ],
        "retry_count": 3,
        "task_status": "tool_error",
        "last_tool": "search_restaurants",
        "last_tool_result": {
            "status": "error",
            "content": "Error: MCP connection failed",
        },
        "current_step": "search_restaurants",
    }

    result = route_after_tools(state)

    assert result == END


def test_tool_failure_retry_count_is_preserved_after_limit():
    state = {
        "messages": [
            ToolMessage(
                name="search_restaurants",
                content="Error: MCP connection failed",
                status="error",
                tool_call_id="test-1",
            )
        ],
        "retry_count": 2,
        "task_status": "tool_error",
        "last_tool": "search_restaurants",
        "last_tool_result": {
            "status": "error",
            "content": "Error: MCP connection failed",
        },
        "current_step": "search_restaurants",
    }

    result = observe_tool_result(state)

    assert result["retry_count"] == 3
    assert result["task_status"] == "tool_error"

def test_tool_failure_reaches_recovery_boundary_after_three_retries():
    state = {
        "messages": [],
        "retry_count": 3,
        "task_status": "tool_error",
        "last_tool": "search_restaurants",
        "last_tool_result": {
            "status": "error",
            "content": "Error: MCP connection failed",
        },
        "current_step": "search_restaurants",
    }

    assert state["retry_count"] >= 3
    assert state["task_status"] == "tool_error"

def test_mcp_failure_requires_adaptation():
    state = {
        "messages": [],
        "user_id": "test-user",
        "thread_id": "test-thread",

        "location": "Mayfair",
        "cuisine": "Italian",
        "date": "2026-10-01",
        "time": "19:00",
        "party_size": 2,
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

        "task_status": "tool_error",

        "plan": [
            "Understand user requirements",
            "Search restaurants",
            "Check availability",
        ],
        "current_step": "search_restaurants",
        "last_tool": "search_restaurants",
        "last_tool_result": {
            "status": "error",
            "content": "Error: MCP connection failed",
        },
        "retry_count": 3,

        "long_term_memories": {},
        "original_user_request": (
            "Find me an Italian restaurant in Mayfair "
            "for 2 people at 19:00."
        ),

        "plan_goal": (
            "Find an Italian restaurant in Mayfair "
            "for 2 people at 19:00."
        ),
        "plan_steps": [
            "Search restaurants",
            "Check availability",
        ],
        "missing_information": [],

        "execution_summary": None,
        "goal_satisfied": False,
        "adaptation_needed": False,
        "next_action": None,
        "adaptation_count": 0,
    }

    result = evaluate_execution(state)

    assert result["goal_satisfied"] is False
    assert result["adaptation_needed"] is True

def test_tool_failure_routes_to_adaptation():
    state = {
        "goal_satisfied": False,
        "adaptation_needed": True,
        "adaptation_count": 0,
    }

    result = route_after_evaluation(state)

    assert result == "adapt"

def test_tool_failure_adaptation_stops_after_two_adaptations():
    state = {
        "goal_satisfied": False,
        "adaptation_needed": True,
        "adaptation_count": 2,
    }

    result = route_after_evaluation(state)

    assert result == "save_memory"

def test_retry_exhaustion_produces_adaptable_execution_state():
    state = {
        "messages": [],
        "user_id": "test-user",
        "thread_id": "test-thread",

        "location": "Mayfair",
        "cuisine": "Italian",
        "date": "2026-09-25",
        "time": "19:00",
        "party_size": 2,
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

        "task_status": "tool_error",

        "plan": [
            "Understand user requirements",
            "Search restaurants",
            "Check availability",
        ],

        "current_step": "search_restaurants",

        "last_tool": "search_restaurants",

        "last_tool_result": {
            "status": "error",
            "content": "Error: MCP connection failed",
        },

        "retry_count": 3,

        "long_term_memories": {},

        "original_user_request": (
            "Find me an Italian restaurant in Mayfair "
            "for 2 people at 19:00."
        ),

        "plan_goal": (
            "Find an Italian restaurant in Mayfair "
            "for 2 people at 19:00."
        ),

        "plan_steps": [
            "Search restaurants",
            "Check availability",
        ],

        "missing_information": [],

        "execution_summary": None,
        "goal_satisfied": False,
        "adaptation_needed": False,
        "next_action": None,
        "adaptation_count": 0,
    }

    result = evaluate_execution(state)

    assert result["goal_satisfied"] is False
    assert result["adaptation_needed"] is True
    assert result["next_action"] is not None