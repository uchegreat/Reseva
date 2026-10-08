from typing import Optional, Annotated
from typing_extensions import TypedDict

from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, BaseMessage

from agent.state import ResevaState
from agent.graph import builder as core_builder
from agent.claude import llm
from agent.memory_extractor import extract_memory

from database.db import SessionLocal
from database.models import User
from database.memory_repository import (
    get_user_memories,
    save_memory,
)


# ============================================================
# STUDIO CHAT INPUT
# ============================================================

class ResevaInputState(TypedDict):
    """
    Minimal input schema exposed to LangGraph Studio.

    The messages field uses LangGraph's add_messages reducer so
    Studio recognizes this graph as a chat-capable graph.
    """

    messages: Annotated[list[BaseMessage], add_messages]


# ============================================================
# RESERVATION PLAN
# ============================================================

class ReservationPlan(BaseModel):
    """
    Structured plan created by Reseva before executing a request.
    """

    goal: str = Field(
        description="The user's overall restaurant reservation goal."
    )

    steps: list[str] = Field(
        description=(
            "Ordered high-level steps Reseva should take to accomplish "
            "the user's goal."
        )
    )

    missing_information: list[str] = Field(
        default_factory=list,
        description=(
            "Information that is genuinely required but missing. "
            "Do not invent values."
        )
    )


# ============================================================
# EXECUTION EVALUATION
# ============================================================

class ExecutionEvaluation(BaseModel):
    """
    Structured evaluation of what happened during execution.
    """

    execution_summary: str = Field(
        description=(
            "A concise summary of what Reseva accomplished during "
            "the latest execution."
        )
    )

    goal_satisfied: bool = Field(
        description=(
            "True only when the user's current request has actually "
            "been satisfied."
        )
    )

    adaptation_needed: bool = Field(
        description=(
            "True when Reseva needs to change or extend its plan "
            "before continuing."
        )
    )

    next_action: Optional[str] = Field(
        default=None,
        description=(
            "The next action Reseva should take if the goal is not "
            "yet satisfied."
        ),
    )


# ============================================================
# ADVANCED STATE
# ============================================================

class AdvancedResevaState(ResevaState):
    """
    Extended state for the advanced Reseva agent.

    The stable reservation state remains unchanged.

    The advanced layer adds:

    - long-term memory
    - original user request
    - autonomous planning
    - execution observation
    - adaptive planning
    - Resend email workflow support through the core graph
    - loop protection
    """

    long_term_memories: dict[str, str]
    original_user_request: str | None
    requested_restaurant_id: str | None

    plan_goal: str | None
    plan_steps: list[str]
    missing_information: list[str]

    execution_summary: str | None
    goal_satisfied: bool
    adaptation_needed: bool
    next_action: str | None

    adaptation_count: int


# ============================================================
# LOAD LONG-TERM MEMORY
# ============================================================

def load_long_term_memory(state: AdvancedResevaState):
    """
    Load the user's long-term preferences from PostgreSQL.

    Preserve the original user request across graph resumes.
    Once original_user_request exists in state, do not overwrite it
    with later human messages created during an interrupt/resume cycle.
    """

    user_id = state.get("user_id") or "studio-user"

    # TEMPORARY DEBUG:
    # Show which user ID LangGraph Studio is actually providing.
    print("DEBUG MEMORY user_id:", repr(user_id))

    # IMPORTANT:
    # Preserve the original request if it has already been captured.
    # This prevents approval/resume messages from replacing the
    # user's actual restaurant request.
    original_user_request = state.get("original_user_request")

    if not original_user_request:
        messages = state.get("messages", [])

        for message in messages:
            if getattr(message, "type", None) == "human":
                content = getattr(message, "content", None)

                if isinstance(content, str) and content.strip():
                    original_user_request = content
                    break

                if isinstance(content, list):
                    text_parts = []

                    for item in content:
                        if isinstance(item, str):
                            text_parts.append(item)

                        elif isinstance(item, dict):
                            text = item.get("text")
                            if isinstance(text, str):
                                text_parts.append(text)

                    if text_parts:
                        original_user_request = " ".join(text_parts)
                        break

    if not user_id:
        return {
            "long_term_memories": {},
            "original_user_request": original_user_request,
        }

    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.external_id == user_id)
            .first()
        )

        if not user:
            print(
                "DEBUG MEMORY: No User found for external_id:",
                repr(user_id),
            )

            return {
                "long_term_memories": {},
                "original_user_request": original_user_request,
            }

        print(
            "DEBUG MEMORY: User found:",
            user.id,
            repr(user.external_id),
        )

        memories = get_user_memories(
            db=db,
            user_id=user.id,
        )

        memory_context = {
            memory.memory_key: memory.memory_value
            for memory in memories
        }

        print(
            "DEBUG MEMORY: Loaded memories:",
            memory_context,
        )

        return {
            "long_term_memories": memory_context,
            "original_user_request": original_user_request,
        }

    finally:
        db.close()

def detect_requested_restaurant(state: AdvancedResevaState):
    """
    Detect the restaurant to use for the reservation.

    Priority:
    1. Explicit restaurant named in the current user request.
    2. Long-term preferred restaurant.
    """

    user_request = state.get("original_user_request") or ""

    if isinstance(user_request, list):
        text_parts = []

        for item in user_request:
            if isinstance(item, str):
                text_parts.append(item)

            elif isinstance(item, dict):
                content = item.get("content")

                if isinstance(content, str):
                    text_parts.append(content)

        user_request = " ".join(text_parts)

    elif not isinstance(user_request, str):
        user_request = str(user_request)

    restaurant_map = {
        "bella italia mayfair": "rest-001",
        "la tavola": "rest-002",
        "the mayfair grill": "rest-003",
        "sushi house mayfair": "rest-004",
    }

    request_lower = user_request.lower()

    # --------------------------------------------------------
    # 1. Explicit restaurant in the user's request
    # --------------------------------------------------------

    for restaurant_name, restaurant_id in restaurant_map.items():
        if restaurant_name in request_lower:
            return {
                "requested_restaurant_id": restaurant_id,
                "selected_restaurant_id": restaurant_id,
            }

    # --------------------------------------------------------
    # 2. Use long-term preferred restaurant
    # --------------------------------------------------------

    memories = state.get("long_term_memories", {})

    preferred_restaurant = memories.get(
        "preferred_restaurant"
    )

    if preferred_restaurant:
        preferred_lower = preferred_restaurant.lower().strip()

        for restaurant_name, restaurant_id in restaurant_map.items():
            if restaurant_name in preferred_lower:
                return {
                    "requested_restaurant_id": restaurant_id,
                    "selected_restaurant_id": restaurant_id,
                }

    return {}


# ============================================================
# CREATE INITIAL PLAN
# ============================================================

def create_reservation_plan(state: AdvancedResevaState):
    """
    Create an explicit plan for the user's request.

    This is the first planning layer of the deep agent.

    The planner does NOT book anything.
    It only determines the steps required to accomplish
    the user's goal.
    """

    user_request = state.get("original_user_request")

    if not user_request:
        return {
            "plan_goal": None,
            "plan_steps": [],
            "missing_information": [],
        }

    memories = state.get("long_term_memories", {})

    memory_context = "\n".join(
        f"- {key}: {value}"
        for key, value in memories.items()
    )

    prompt = f"""
You are the planning component of Reseva, an autonomous
restaurant reservation agent.

Your job is to create a practical plan for accomplishing
the user's current restaurant-related request.

USER REQUEST:
{user_request}

KNOWN LONG-TERM USER PREFERENCES:
{memory_context or "None"}

CURRENT RESERVATION STATE:
Location: {state.get("location")}
Cuisine: {state.get("cuisine")}
Date: {state.get("date")}
Time: {state.get("time")}
Party size: {state.get("party_size")}
Budget: {state.get("budget")}
Selected restaurant: {state.get("selected_restaurant_id")}

PLANNING RULES:
1. Do not invent missing information.
2. Do not claim that a restaurant is available.
3. Do not claim that a reservation has been made.
4. Do not perform any booking yourself.
5. Create high-level actionable steps.
6. Use long-term preferences only when relevant.
7. If important information is missing, identify it.
8. The plan should adapt to the user's current request.
9. A booking requires explicit user approval.
10. Keep the plan concise and practical.
11. If long-term preferences contain a preferred_restaurant,
    treat that restaurant as the user's restaurant choice unless
    the user explicitly names a different restaurant.
12. Do not list restaurant name as missing information when
    preferred_restaurant is available.

Examples of possible steps:
- Clarify missing reservation information.
- Search restaurants matching the user's requirements.
- Compare suitable restaurant options.
- Check availability.
- Find alternative times if necessary.
- Present options to the user.
- Request booking approval.
- Create the reservation after approval.
- Confirm the reservation.

Return a structured plan.
"""

    plan = llm.with_structured_output(
        ReservationPlan
    ).invoke(prompt)

    return {
        "plan_goal": plan.goal,
        "plan_steps": plan.steps,
        "missing_information": plan.missing_information,
        "adaptation_count": 0,
    }


# ============================================================
# INJECT MEMORY + PLAN
# ============================================================

def inject_memory_and_plan(state: AdvancedResevaState):
    """
    Add long-term memory and the current execution plan
    to the user's message.

    We do NOT add another SystemMessage because graph.py
    already creates the system message for Claude.

    The original user request is always used when rebuilding
    the enriched message. This prevents repeated adaptive
    iterations from nesting previous plans inside one another.
    """

    memories = state.get("long_term_memories", {})
    plan_goal = state.get("plan_goal")
    plan_steps = state.get("plan_steps", [])
    missing_information = state.get(
        "missing_information",
        [],
    )

    original_user_request = state.get(
        "original_user_request"
    )

    messages = state.get("messages", [])

    if not messages:
        return {}

    latest_user_message = None

    for message in reversed(messages):
        if getattr(message, "type", None) == "human":
            latest_user_message = message
            break

    if latest_user_message is None:
        return {}

    sections = []

    if memories:
        memory_lines = "\n".join(
            f"- {key}: {value}"
            for key, value in memories.items()
        )

        sections.append(
            "RESEVA LONG-TERM USER PREFERENCES:\n"
            f"{memory_lines}"
        )

    if plan_goal:
        sections.append(
            "RESEVA EXECUTION PLAN:\n"
            f"Goal: {plan_goal}"
        )

    if plan_steps:
        plan_lines = "\n".join(
            f"{index}. {step}"
            for index, step in enumerate(
                plan_steps,
                start=1,
            )
        )

        sections.append(
            f"Plan steps:\n{plan_lines}"
        )

    if missing_information:
        missing_lines = "\n".join(
            f"- {item}"
            for item in missing_information
        )

        sections.append(
            "INFORMATION CURRENTLY MISSING:\n"
            f"{missing_lines}"
        )

    execution_summary = state.get(
        "execution_summary"
    )

    if execution_summary:
        sections.append(
            "LATEST EXECUTION RESULT:\n"
            f"{execution_summary}"
        )

    next_action = state.get("next_action")

    if next_action:
        sections.append(
            "NEXT ADAPTIVE ACTION:\n"
            f"{next_action}"
        )

    if not sections:
        return {}

    user_request = (
        original_user_request
        or latest_user_message.content
    )

    enriched_content = (
    "\n\n".join(sections)
    + "\n\n"
    "Use this context to help execute the user's request.\n"
    "The plan is guidance, not a completed action.\n"
    "You must still follow the reservation workflow.\n"
    "You must never claim that a booking exists unless the "
    "booking tool actually succeeds.\n\n"
    "IMPORTANT USER PREFERENCES AND CONSTRAINTS:\n"
    "- If the user explicitly names a restaurant, that restaurant "
    "is the user's required choice.\n"
    "- Do NOT substitute another restaurant.\n"
    "- Do NOT recommend or select a different restaurant when the "
    "user has explicitly requested one.\n"
    "- If the requested restaurant is unavailable, keep that "
    "restaurant as the selected restaurant and handle the "
    "unavailability through the recovery/alternative-time workflow.\n"
    "- Only change the restaurant if the user explicitly asks for "
    "another restaurant or agrees to an alternative.\n\n"
    "CURRENT USER REQUEST:\n"
    f"{user_request}"
)

    enriched_message = HumanMessage(
        content=enriched_content,
        id=latest_user_message.id,
    )

    updated_messages = list(messages)

    for index in range(
        len(updated_messages) - 1,
        -1,
        -1,
    ):
        if getattr(
            updated_messages[index],
            "type",
            None,
        ) == "human":
            updated_messages[index] = enriched_message
            break

    return {
        "messages": updated_messages,
    }


# ============================================================
# RUN CORE RESERVATION AGENT
# ============================================================

async def run_core_reservation_agent(
    state: AdvancedResevaState,
    config=None,
):
    """
    Run the existing stable Reseva reservation graph
    asynchronously so that MCP tools can execute correctly.

    The parent advanced graph passes the same LangGraph
    configuration through to the core graph so that the
    conversation thread remains consistent.
    """

    core_graph = core_builder.compile()

    core_state = dict(state)

    # If the advanced layer detected that the user explicitly
    # requested a restaurant, preserve that selection when
    # entering the core reservation graph.
    if state.get("requested_restaurant_id"):
        core_state["selected_restaurant_id"] = state.get(
            "requested_restaurant_id"
        )

    result = await core_graph.ainvoke(
        core_state,
        config=config,
    )

    return result


# ============================================================
# EVALUATE EXECUTION
# ============================================================

def evaluate_execution(
    state: AdvancedResevaState,
):
    """
    Observe what the core reservation agent accomplished
    and determine whether adaptation is required.
    """

    user_request = state.get(
        "original_user_request"
    )

    prompt = f"""
You are the execution evaluator for Reseva.

Your job is to observe the latest execution and determine
whether the user's request has been satisfied.

ORIGINAL USER REQUEST:
{user_request}

CURRENT RESERVATION STATE:
Location: {state.get("location")}
Cuisine: {state.get("cuisine")}
Date: {state.get("date")}
Time: {state.get("time")}
Party size: {state.get("party_size")}
Budget: {state.get("budget")}
Selected restaurant: {state.get("selected_restaurant_id")}
Reservation ID: {state.get("reservation_id")}
Reservation status: {state.get("reservation_status")}
Task status: {state.get("task_status")}

AVAILABLE RESTAURANTS:
{state.get("available_restaurants")}

AVAILABILITY RESULTS:
{state.get("availability_results")}

CURRENT PLAN:
Goal: {state.get("plan_goal")}
Steps: {state.get("plan_steps")}
Missing information: {state.get("missing_information")}

Evaluate the execution.

RULES:
1. Determine whether the user's actual request has been satisfied.
2. Never claim a reservation exists unless reservation_status
   confirms it.
3. If the requested time is unavailable but alternatives exist,
   the goal is not yet satisfied.
4. If the user still needs to choose an alternative,
   the goal is not yet satisfied.
5. If important information is missing, the goal is not satisfied.
6. If the request only requires finding restaurant options and
   suitable options were successfully found, that search goal
   may be considered satisfied.
7. If the reservation was successfully created and the request
   is complete, goal_satisfied should be true.
8. If another action is required, set adaptation_needed to true.
9. next_action should describe the concrete next action.
10. Do not invent facts.

Return a structured evaluation.
"""

    evaluation = llm.with_structured_output(
        ExecutionEvaluation
    ).invoke(prompt)

    return {
        "execution_summary": evaluation.execution_summary,
        "goal_satisfied": evaluation.goal_satisfied,
        "adaptation_needed": evaluation.adaptation_needed,
        "next_action": evaluation.next_action,
    }


# ============================================================
# ADAPTIVE PLAN
# ============================================================

def adapt_plan(
    state: AdvancedResevaState,
):
    """
    Re-plan using the result of the previous execution.

    This is what turns the advanced graph from:

        Plan -> Execute

    into:

        Plan -> Execute -> Observe -> Adapt -> Execute
    """

    current_count = state.get(
        "adaptation_count",
        0,
    )

    prompt = f"""
You are Reseva's adaptive planning component.

The original plan was executed, but the user's request
has not yet been completely satisfied.

ORIGINAL USER REQUEST:
{state.get("original_user_request")}

CURRENT PLAN:
Goal: {state.get("plan_goal")}
Steps: {state.get("plan_steps")}

EXECUTION RESULT:
{state.get("execution_summary")}

NEXT ACTION IDENTIFIED:
{state.get("next_action")}

CURRENT RESERVATION STATE:
Location: {state.get("location")}
Cuisine: {state.get("cuisine")}
Date: {state.get("date")}
Time: {state.get("time")}
Party size: {state.get("party_size")}
Budget: {state.get("budget")}
Selected restaurant: {state.get("selected_restaurant_id")}
Reservation ID: {state.get("reservation_id")}
Reservation status: {state.get("reservation_status")}
Task status: {state.get("task_status")}

AVAILABLE RESTAURANTS:
{state.get("available_restaurants")}

AVAILABILITY RESULTS:
{state.get("availability_results")}

Create an updated execution plan.

RULES:
1. Use information discovered during the previous execution.
2. Do not blindly repeat an action that already failed.
3. If the requested time is unavailable, consider the
   available alternatives.
4. If the user must make a choice, identify that clearly.
5. Never invent restaurant availability.
6. Never claim that a reservation exists unless confirmed.
7. Do not perform the booking yourself.
8. Keep the new plan practical and concise.
9. Preserve already-known reservation information.
10. The plan should move Reseva closer to satisfying the
    original user request.

Return a structured plan.
"""

    updated_plan = llm.with_structured_output(
        ReservationPlan
    ).invoke(prompt)

    return {
        "plan_goal": updated_plan.goal,
        "plan_steps": updated_plan.steps,
        "missing_information": updated_plan.missing_information,
        "adaptation_count": current_count + 1,
    }


# ============================================================
# ROUTE AFTER EXECUTION EVALUATION
# ============================================================

def route_after_evaluation(
    state: AdvancedResevaState,
):
    """
    Decide whether Reseva should finish or adapt.

    If the core agent has reached a point where the user must
    provide information or make a decision, stop the current
    execution instead of repeatedly asking the same question.
    """

    if state.get("goal_satisfied") is True:
        return "save_memory"

    task_status = state.get("task_status")

    # The user must provide the next piece of information or
    # make a decision. Do not repeatedly execute the same plan.
    waiting_statuses = {
        "awaiting_user_input",
        "missing_restaurant",
        "missing_date",
        "missing_time",
        "missing_party_size",
        "booking_approval_required",
        "booking_email_required",
        "cancellation_approval_required",
        "modification_approval_required",
        "modification_missing_details",
    }

    if task_status in waiting_statuses:
        return "save_memory"

    adaptation_count = state.get(
        "adaptation_count",
        0,
    )

    if (
        state.get("adaptation_needed") is True
        and adaptation_count < 2
    ):
        return "adapt"

    return "save_memory"


# ============================================================
# SAVE NEW LONG-TERM MEMORY
# ============================================================

def save_new_long_term_memory(
    state: AdvancedResevaState,
):
    """
    Save explicit long-term memories from the original user request.

    Supports:
    - user_name
    - preferred_restaurant
    - preferred_cuisine
    - preferred_location
    - typical_party_size
    - budget_preference
    """

    original_user_message = state.get("original_user_request")

    if not original_user_message:
        return {}

    user_id = state.get("user_id") or "studio-user"

    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.external_id == user_id)
            .first()
        )

        if not user:
            return {}

        # --------------------------------------------------------
        # Extract the primary memory using the existing extractor
        # --------------------------------------------------------

        memory_update = extract_memory(
            original_user_message
        )

        if (
            memory_update.memory_type
            and memory_update.memory_key
            and memory_update.memory_value
        ):
            save_memory(
                db=db,
                user_id=user.id,
                memory_type=memory_update.memory_type,
                memory_key=memory_update.memory_key,
                memory_value=memory_update.memory_value,
            )

        # --------------------------------------------------------
        # Explicit user name
        # --------------------------------------------------------

        import re

        name_match = re.search(
            r"\b(?:my name is|you can call me)\s+([A-Za-z][A-Za-z'-]*)\b",
            original_user_message,
            re.IGNORECASE,
        )

        if name_match:
            user_name = name_match.group(1).strip()

            save_memory(
                db=db,
                user_id=user.id,
                memory_type="profile",
                memory_key="user_name",
                memory_value=user_name,
            )

        # --------------------------------------------------------
        # Explicit preferred restaurant
        # --------------------------------------------------------

        restaurant_match = re.search(
            r"\bmy preferred restaurant is\s+(.+?)(?:\.|$)",
            original_user_message,
            re.IGNORECASE,
        )

        if restaurant_match:
            preferred_restaurant = (
                restaurant_match.group(1)
                .strip()
            )

            save_memory(
                db=db,
                user_id=user.id,
                memory_type="preference",
                memory_key="preferred_restaurant",
                memory_value=preferred_restaurant,
            )

        return {}

    finally:
        db.close()


def is_memory_only_request(state: AdvancedResevaState):
    """Detect requests that only ask Reseva to remember information."""
    original_request = state.get("original_user_request") or ""

    memory_update = extract_memory(original_request)

    if (
        memory_update.memory_type
        and memory_update.memory_key
        and memory_update.memory_value
    ):
        return "save_memory"

    return "continue"


# ============================================================
# BUILD ADVANCED GRAPH
# ============================================================

def build_advanced_graph():
    """
    Build the advanced Reseva graph.

    Deep-agent flow:

        START
          ↓
        load_memory
          ↓
        create_plan
          ↓
        inject_memory_and_plan
          ↓
        core_agent
          ↓
        evaluate_execution
          ↓
        ┌───────────────────────────┐
        │                           │
        │ Goal satisfied            │ Adaptation needed
        │                           │
        ▼                           ▼
      save_memory               adapt_plan
        │                           │
        ▼                           ▼
       END                inject_memory_and_plan
                                    │
                                    ▼
                                core_agent
    """

    graph = StateGraph(
        AdvancedResevaState,
        input_schema=ResevaInputState,
    )

    # --------------------------------------------------------
    # Nodes
    # --------------------------------------------------------

    graph.add_node(
        "load_memory",
        load_long_term_memory,
    )

    graph.add_node(
        "create_plan",
        create_reservation_plan,
    )

    graph.add_node(
        "detect_requested_restaurant",
        detect_requested_restaurant,
    )

    graph.add_node(
        "inject_memory_and_plan",
        inject_memory_and_plan,
    )


    graph.add_node(
        "core_agent",
        run_core_reservation_agent,
    )

    graph.add_node(
        "evaluate_execution",
        evaluate_execution,
    )

    graph.add_node(
        "adapt",
        adapt_plan,
    )

    graph.add_node(
        "save_memory",
        save_new_long_term_memory,
    )

    # --------------------------------------------------------
    # Initial execution path
    # --------------------------------------------------------

    graph.add_conditional_edges(
    START,
    is_memory_only_request,
    {
        "save_memory": "save_memory",
        "continue": "load_memory",
    },
)

    graph.add_edge(
        "load_memory",
        "create_plan",
    )

    graph.add_edge(
        "create_plan",
        "detect_requested_restaurant",
    )

    graph.add_edge(
        "detect_requested_restaurant",
        "inject_memory_and_plan",
    )

    graph.add_edge(
        "inject_memory_and_plan",
        "core_agent",
    )

    # --------------------------------------------------------
    # Observe execution
    # --------------------------------------------------------

    graph.add_edge(
        "core_agent",
        "evaluate_execution",
    )

    # --------------------------------------------------------
    # Adaptive routing
    # --------------------------------------------------------

    graph.add_conditional_edges(
        "evaluate_execution",
        route_after_evaluation,
        {
            "adapt": "adapt",
            "save_memory": "save_memory",
        },
    )

    # --------------------------------------------------------
    # Re-plan and execute again
    # --------------------------------------------------------

    graph.add_edge(
        "adapt",
        "inject_memory_and_plan",
    )

    # --------------------------------------------------------
    # Finish
    # --------------------------------------------------------

    graph.add_edge(
        "save_memory",
        END,
    )

    return graph



# ============================================================
# GRAPH BUILDER
# ============================================================

builder = build_advanced_graph()

def compile_advanced_graph(checkpointer=None):
    graph = build_advanced_graph()

    return graph.compile(
        checkpointer=checkpointer
    )


