
import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from agent.graph import (
    observe_tool_result,
    route_after_tools,
)
from agent.state import ResevaState


@pytest.mark.anyio
async def test_mcp_failure_reaches_graph_recovery_boundary():
    """
    Verify the real LangGraph ToolNode failure behavior:

        failing tool
            ↓
        ToolNode
            ↓
        ToolMessage(status="error")
            ↓
        observe_tool_result
            ↓
        retry_count
            ↓
        retry boundary
    """

    async def failing_search_restaurants(
        location: str,
        cuisine: str | None = None,
    ):
        raise RuntimeError(
            "Simulated MCP restaurant service failure"
        )

    failing_tool = StructuredTool.from_function(
        coroutine=failing_search_restaurants,
        name="search_restaurants",
        description="Simulated failing restaurant search.",
    )

    def handle_tool_error(error: Exception) -> str:
        """
        Convert the tool exception into an error message so
        ToolNode can continue into observe_tool_result().
        """
        return f"Tool execution failed: {error}"

    # ---------------------------------------------------------
    # BUILD TEST GRAPH
    # ---------------------------------------------------------

    builder = StateGraph(ResevaState)

    async def request_search(state: ResevaState):
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "search_restaurants",
                            "args": {
                                "location": "Mayfair",
                                "cuisine": "Italian",
                            },
                            "id": f"call-{uuid.uuid4()}",
                        }
                    ],
                )
            ]
        }

    builder.add_node(
        "request_search",
        request_search,
    )

    builder.add_node(
        "tools",
        ToolNode(
            [failing_tool],
            handle_tool_errors=handle_tool_error,
        ),
    )

    builder.add_node(
        "observe_tool_result",
        observe_tool_result,
    )

    # ---------------------------------------------------------
    # GRAPH EDGES
    # ---------------------------------------------------------

    builder.add_edge(
        START,
        "request_search",
    )

    builder.add_edge(
        "request_search",
        "tools",
    )

    builder.add_edge(
        "tools",
        "observe_tool_result",
    )

    builder.add_conditional_edges(
        "observe_tool_result",
        route_after_tools,
        {
            "agent": END,
            "store_search_results": END,
            "store_availability_results": END,
            "alternative_times": END,
            END: END,
        },
    )

    graph = builder.compile(
        checkpointer=MemorySaver(),
    )

    # ---------------------------------------------------------
    # CONFIG
    # ---------------------------------------------------------

    thread_id = f"mcp-failure-{uuid.uuid4()}"

    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    # ---------------------------------------------------------
    # INITIAL STATE
    # ---------------------------------------------------------

    initial_state = {
        "messages": [
            HumanMessage(
                content="Find me an Italian restaurant in Mayfair."
            )
        ],
        "user_id": "mcp-failure-test-user",
        "thread_id": thread_id,

        "location": "Mayfair",
        "cuisine": "Italian",
        "date": None,
        "time": None,
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

        "task_status": "started",

        "plan": [],
        "current_step": None,
        "last_tool": None,
        "last_tool_result": None,
        "retry_count": 0,
    }

    # ---------------------------------------------------------
    # RUN GRAPH
    # ---------------------------------------------------------

    result = await graph.ainvoke(
        initial_state,
        config=config,
    )

    # ---------------------------------------------------------
    # DEBUG OUTPUT
    # ---------------------------------------------------------

    print("\n--- MCP FAILURE TOOLNODE INTEGRATION ---")

    print(
        "Task status:",
        result.get("task_status"),
    )

    print(
        "Retry count:",
        result.get("retry_count"),
    )

    print(
        "Last tool:",
        result.get("last_tool"),
    )

    print(
        "Last tool result:",
        result.get("last_tool_result"),
    )

    # ---------------------------------------------------------
    # ASSERTIONS
    # ---------------------------------------------------------

    assert result.get("last_tool") == "search_restaurants"

    assert result.get("task_status") == "tool_error"

    assert result.get("retry_count") == 1

    assert result.get("last_tool_result") is not None

