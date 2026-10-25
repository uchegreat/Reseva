import json
import os
import re
import requests
from database.db import SessionLocal
from database.repository import save_reservation

from langgraph.types import interrupt
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from langchain_core.messages import SystemMessage

from agent.state import ResevaState
from agent.claude import llm_with_tools

from agent.mcp_client import (
    search_restaurants,
    check_availability,
    get_alternative_times,
    create_reservation,
    get_reservation,
    modify_reservation,
    cancel_reservation,
)

from agent.extractor import extract_reservation_update


# ---------------------------------------------------------
# TOOLS
# ---------------------------------------------------------

# create_reservation is included here so the MCP client is
# available to the graph.

# Claude is NOT bound to create_reservation.
# Actual booking is controlled by the graph and requires
# explicit human approval.

tools = [
    search_restaurants,
    check_availability,
    get_alternative_times,
    create_reservation,
]

# ---------------------------------------------------------
# SENDER EMAIL
# ---------------------------------------------------------

RESEND_API_URL = "https://api.resend.com/emails"

def _get_customer_email(state: ResevaState) -> str | None:
    lookup = state.get("reservation_lookup") or {}
    email = lookup.get("customer_email")
    return email.strip() if isinstance(email, str) and email.strip() else None

def _valid_email(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value.strip()) is not None

def _is_approved(value) -> bool:
    """True for a boolean approval (React app) or a yes-style string (Studio)."""
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"yes", "y", "true", "approve", "approved"}
    return False

def _store_customer_email(state: ResevaState, email: str) -> dict:
    lookup = dict(state.get("reservation_lookup") or {})
    lookup["customer_email"] = email
    return {"reservation_lookup": lookup}

def _send_resend_email(*, to_email: str, subject: str, text_body: str, html_body: str) -> dict:
    """Send transactional email through Resend's HTTPS REST API. No SMTP."""
    token = os.getenv("RESEND_API_KEY")
    from_email = os.getenv("RESEND_FROM_EMAIL")
    from_name = os.getenv("RESEND_FROM_NAME", "Reseva")
    if not token or not from_email:
        return {"success": False, "error": "RESEND_API_KEY and RESEND_FROM_EMAIL must be configured."}
    try:
        response = requests.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "from": f"{from_name} <{from_email}>" if from_name else from_email,
                "to": [to_email],
                "subject": subject,
                "text": text_body,
                "html": html_body,
            },
            timeout=20,
        )
    except requests.RequestException as exc:
        return {"success": False, "error": f"Resend request failed: {exc}"}
    try:
        data = response.json()
    except ValueError:
        data = {"raw": response.text}
    if 200 <= response.status_code < 300:
        return {"success": True, "response": data}
    return {"success": False, "status_code": response.status_code, "error": data}


def booking_email_request(state: ResevaState):
    """Collect the customer email before explicit booking approval."""
    if _get_customer_email(state):
        return {"task_status": "booking_email_collected"}
    email = interrupt({
        "type": "email_request",
        "purpose": "booking_confirmation",
        "message": "What email address should I use for your reservation confirmation?",
    })
    if not _valid_email(email):
        return {"task_status": "email_invalid"}
    return {**_store_customer_email(state, email.strip()), "task_status": "booking_email_collected"}


def route_after_booking_email(state: ResevaState):
    """
    Decide whether to create the reservation after a valid
    customer email has been collected.
    """
    if state.get("task_status") == "booking_email_collected":
        return "create_reservation"

    return "end"


def cancellation_email_request(state: ResevaState):
    """Collect the customer email before explicit cancellation approval."""
    if _get_customer_email(state):
        return {"task_status": "cancellation_email_collected"}
    email = interrupt({
        "type": "email_request",
        "purpose": "cancellation_confirmation",
        "message": "What email address should I use for your cancellation confirmation?",
    })
    if not _valid_email(email):
        return {"task_status": "email_invalid"}
    return {**_store_customer_email(state, email.strip()), "task_status": "cancellation_email_collected"}


def route_after_cancellation_email(state: ResevaState):
    return "cancellation_approval" if state.get("task_status") == "cancellation_email_collected" else "end"


# ---------------------------------------------------------
# AUTONOMOUS PLANNING
# ---------------------------------------------------------

def create_agent_plan(state: ResevaState):
    """
    Create or update the execution plan for the current
    reservation task.

    The plan is persisted in graph state so it survives
    thread pauses and resumes.
    """

    # ---------------------------------------------------------
    # EXISTING PLAN
    # ---------------------------------------------------------

    existing_plan = state.get("plan") or []

    # If a plan already exists, preserve it rather than
    # recreating the entire plan on every user message.
    if existing_plan:

        current_step = state.get("current_step")

        if state.get("booking_requested") is True:
            current_step = "Request explicit booking approval"

        elif state.get("reservation_status") == "confirmed":
            current_step = "Verify the reservation result"

        elif state.get("task_status") == "waiting_for_selection":
            current_step = "Wait for restaurant and time selection"

        elif state.get("task_status") == "availability_confirmed":
            current_step = "Present suitable options to the user"

        return {
            "plan": existing_plan,
            "current_step": current_step,
        }

    # ---------------------------------------------------------
    # CREATE INITIAL PLAN
    # ---------------------------------------------------------

    if state.get("cancellation_requested") is True:

        plan = [
            "Identify the reservation to cancel",
            "Retrieve the existing reservation",
            "Request explicit cancellation approval",
            "Cancel the reservation after approval",
            "Verify the cancellation result",
        ]

    elif state.get("modification_requested") is True:

        plan = [
            "Identify the reservation to modify",
            "Retrieve the existing reservation",
            "Determine the requested changes",
            "Check availability for the new details",
            "Request explicit modification approval",
            "Modify the reservation after approval",
            "Verify the modification result",
        ]

    else:

        plan = [
            "Understand the user's restaurant requirements",
            "Search for suitable restaurants",
            "Check availability for suitable restaurants",
            "Handle unavailable restaurants or times",
            "Present suitable options to the user",
            "Wait for restaurant and time selection",
            "Request explicit booking approval",
            "Create the reservation after approval",
            "Verify the reservation result",
        ]

    return {
        "plan": plan,
        "current_step": plan[0] if plan else None,
        "retry_count": 0,
    }

# ---------------------------------------------------------
# STATE EXTRACTION
# ---------------------------------------------------------

def extract_state(state: ResevaState):

    latest_message = state["messages"][-1]

    update = extract_reservation_update(
        latest_message.content,
        state,
    )

    updates = {}

    for field in [
        "location",
        "cuisine",
        "date",
        "time",
        "party_size",
        "budget",
        "selected_restaurant_id",
        "booking_requested",
        "modification_requested",
        "reservation_id_to_modify",
        "modification_date",
        "modification_time",
        "modification_party_size",
        "cancellation_requested",
    ]:
        value = getattr(update, field)

        if value is not None:

            # IMPORTANT:
            # If the advanced graph has already established an
            # explicit restaurant selection, do not allow the
            # extractor to replace it with another restaurant.
            if (
                field == "selected_restaurant_id"
                and state.get("selected_restaurant_id")
            ):
                continue

            updates[field] = value

    # ---------------------------------------------------------
    # EXPLICIT BOOKING REQUEST DETECTION
    # ---------------------------------------------------------

    latest_user_text = str(
        latest_message.content
    ).lower().strip()

    booking_keywords = (
        "book",
        "booking",
        "reserve",
        "reservation",
    )

    explicit_booking_request = any(
        keyword in latest_user_text
        for keyword in booking_keywords
    )

    if explicit_booking_request:
        updates["booking_requested"] = True

        if not updates.get("selected_restaurant_id"):
            existing_restaurant = state.get(
                "selected_restaurant_id"
            )

            if existing_restaurant:
                updates["selected_restaurant_id"] = (
                    existing_restaurant
                )

    # ---------------------------------------------------------
    # EXISTING CANCELLATION LOGIC
    # ---------------------------------------------------------

    if updates.get("cancellation_requested") is True:

        if not updates.get("reservation_id_to_modify"):

            existing_reservation_id = state.get(
                "reservation_id"
            )

            if existing_reservation_id:
                updates["reservation_id_to_modify"] = (
                    existing_reservation_id
                )

    # ---------------------------------------------------------
    # RESOLVE RESTAURANT FOR AVAILABILITY RECOVERY
    # ---------------------------------------------------------

    selected_restaurant_id = updates.get(
        "selected_restaurant_id",
        state.get("selected_restaurant_id"),
    )

    requested_time = updates.get(
        "time",
        state.get("time"),
    )

    if selected_restaurant_id:

        availability_results = state.get(
            "availability_results",
            [],
        )

        selected_result = next(
            (
                result
                for result in reversed(availability_results)
                if (
                    result.get("restaurant_id")
                    == selected_restaurant_id
                    and result.get("available") is False
                    and result.get("alternative_times")
                    and (
                        requested_time is None
                        or result.get("time") == requested_time
                    )
                )
            ),
            None,
        )

        if selected_result:
            updates["task_status"] = "recovery_needed"

    # ---------------------------------------------------------
    # NEW TIME REQUIRES FRESH AVAILABILITY CHECK
    # ---------------------------------------------------------

    if update.time is not None:
        updates["task_status"] = "processing"

    return updates

# ---------------------------------------------------------
# CHECK SELECTED RESTAURANT AT NEW TIME
# ---------------------------------------------------------

async def check_selected_restaurant_node(state: ResevaState):
    """
    Deterministically check availability for the currently selected
    restaurant.

    If a restaurant has already been explicitly selected, this node
    must use that restaurant ID and must not allow the LLM to choose
    another restaurant.
    """

    restaurant_id = state.get("selected_restaurant_id")
    date = state.get("date")
    time = state.get("time")
    party_size = state.get("party_size")

    if not restaurant_id:
        return {
            "task_status": "processing",
        }

    if not date or not time or not party_size:
        return {
            "task_status": "processing",
        }

    result = await check_availability.ainvoke(
        {
            "restaurant_id": restaurant_id,
            "date": date,
            "time": time,
            "party_size": party_size,
        }
    )

    return {
        "selected_restaurant_id": restaurant_id,
        "time": time,
        "availability_results": [result],
        "last_tool": "check_availability",
        "last_tool_result": result,
        "current_step": "Evaluate availability",
        "task_status": "processing",
    }


# ---------------------------------------------------------
# ROUTE AFTER NEW TIME CHECK
# ---------------------------------------------------------

def route_after_extract_state(state: ResevaState):
    """
    Decide whether a newly selected time needs a deterministic
    availability check before returning control to Claude.

    This prevents Claude from accidentally relying on an old
    availability result or selecting a different restaurant.
    """

    # Retry email collection after an invalid email response.
    if state.get("task_status") == "email_invalid":
        if state.get("cancellation_requested") is True:
            return "cancellation_email"
        if state.get("booking_requested") is True:
            return "booking_email"

    # Cancellation takes priority over normal reservation routing.
    if state.get("cancellation_requested") is True:
        return "cancellation_lookup"

    # Modification takes priority over normal reservation routing.
    if state.get("modification_requested") is True:
        return "modification_lookup"

    # Existing recovery state must be handled before normal agent
    # routing so alternative times are exposed deterministically.
    if state.get("task_status") == "recovery_needed":
        return "alternative_times"

    # If booking has already been requested and the exact selected
    # restaurant/time is confirmed available, go directly to the
    # approval interrupt.
    if (
        state.get("booking_requested") is True
        and state.get("selected_restaurant_id")
        and state.get("date")
        and state.get("time")
        and state.get("party_size")
    ):
        for result in reversed(state.get("availability_results", [])):
            if (
                result.get("restaurant_id")
                == state.get("selected_restaurant_id")
                and result.get("date")
                == state.get("date")
                and result.get("time")
                == state.get("time")
            ):
                if result.get("available") is True:
                    return "booking_approval"

                break

    selected_restaurant_id = state.get(
        "selected_restaurant_id"
    )

    date = state.get("date")
    time = state.get("time")
    party_size = state.get("party_size")

    # If a restaurant is selected and all reservation details
    # are available, make sure availability is checked
    # deterministically for that exact restaurant.
    if (
        selected_restaurant_id
        and date
        and time
        and party_size
    ):
        availability_results = state.get(
            "availability_results",
            [],
        )

        # Find the most recent availability result for the
        # currently selected restaurant.
        latest_result = None

        for result in reversed(availability_results):
            if (
                result.get("restaurant_id")
                == selected_restaurant_id
            ):
                latest_result = result
                break

        # If there is no result for this restaurant, or the
        # result is for a different date/time, force a fresh
        # deterministic availability check.
        if (
            latest_result is None
            or latest_result.get("date") != date
            or latest_result.get("time") != time
        ):
            return "check_selected_restaurant"

        # We have a result for the exact restaurant/date/time.
        # If it is available and booking was requested, go to
        # the explicit booking approval step.
        if (
            latest_result.get("available") is True
            and state.get("booking_requested") is True
        ):
            return "booking_approval"

    # ---------------------------------------------------------
    # DETERMINISTIC FALLBACK
    # ---------------------------------------------------------
    # If a restaurant is explicitly selected and all reservation
    # details are known, never send the request back to Claude.
    # Force the exact selected restaurant through the deterministic
    # availability check.
    if (
        state.get("selected_restaurant_id")
        and state.get("date")
        and state.get("time")
        and state.get("party_size")
    ):
        return "check_selected_restaurant"

    return "agent"


# ---------------------------------------------------------
# STORE SEARCH RESULTS
# ---------------------------------------------------------

def store_search_results(state: ResevaState):
    """
    Extract the most recent restaurant search results and
    store them in ResevaState.

    If no restaurant has been explicitly selected yet, preserve
    the first restaurant returned by the search as the current
    restaurant for the conversation.

    This allows follow-up requests such as:
        "Book it."

    to refer to the restaurant found during the previous step.
    """

    import json

    restaurants = []

    for message in reversed(state["messages"]):

        if getattr(message, "name", None) == "search_restaurants":

            content = message.content

            if isinstance(content, str):
                try:
                    restaurants = json.loads(content)
                except json.JSONDecodeError:
                    restaurants = []

            elif isinstance(content, list):
                restaurants = content

            break

    print("\nStored restaurant results:")
    print(restaurants)

    updates = {
        "available_restaurants": restaurants
    }

    # ---------------------------------------------------------
    # PRESERVE / ESTABLISH CURRENT RESTAURANT
    # ---------------------------------------------------------

    existing_restaurant_id = state.get(
        "selected_restaurant_id"
    )

    if not existing_restaurant_id and restaurants:

        first_restaurant = restaurants[0]

        restaurant_id = first_restaurant.get(
            "id"
        )

        if restaurant_id:
            updates["selected_restaurant_id"] = (
                restaurant_id
            )

            print(
                "\nSelected restaurant:",
                restaurant_id
            )

    return updates



# ---------------------------------------------------------
# STORE AVAILABILITY RESULTS
# ---------------------------------------------------------

def store_availability_results(state: ResevaState):
    """
    Extract availability results from the conversation
    and store them in ResevaState.
    """

    import json

    results = []

    for message in state["messages"]:

        if getattr(message, "name", None) != "check_availability":
            continue

        content = message.content

        if isinstance(content, str):

            try:
                result = json.loads(content)
                results.append(result)

            except json.JSONDecodeError:
                pass

        elif isinstance(content, dict):
            results.append(content)

    print("\nStored availability results:")
    print(results)

    return {
        "availability_results": results
    }


# ---------------------------------------------------------
# ROUTE AFTER AVAILABILITY
# ---------------------------------------------------------

def route_after_availability(state: ResevaState):
    """
    Route based on the most recent availability result.

    Older unavailable results must not trigger recovery after
    the user selects a new time.
    """

    results = state.get(
        "availability_results",
        [],
    )

    if not results:
        return "agent"

    selected_restaurant_id = state.get(
        "selected_restaurant_id"
    )

    # Prefer the latest result for the currently selected
    # restaurant.
    latest_result = None

    if selected_restaurant_id:

        for result in reversed(results):

            if (
                result.get("restaurant_id")
                == selected_restaurant_id
            ):
                latest_result = result
                break

    # If no restaurant is selected, let Claude interpret
    # the complete set of results.
    if latest_result is None:
        return "agent"

    # The current requested time is available.
    if latest_result.get("available") is True:
        return "agent"

    # The current requested time is unavailable and
    # alternatives exist.
    if (
        latest_result.get("available") is False
        and latest_result.get("alternative_times")
    ):
        return "alternative_times"

    return "agent"


# ---------------------------------------------------------
# ALTERNATIVE TIMES
# ---------------------------------------------------------

def alternative_times_node(state: ResevaState):
    """
    Use the already-stored availability result to expose
    alternative times for the selected restaurant.

    We do not call get_alternative_times again because
    check_availability has already returned the alternatives.
    """

    restaurant_id = state.get(
        "selected_restaurant_id"
    )

    if not restaurant_id:
        return {
            "task_status": "alternative_search_failed"
        }

    availability_results = state.get(
        "availability_results",
        []
    )

    selected_result = next(
        (
            result
            for result in reversed(availability_results)
            if (
                result.get("restaurant_id")
                == restaurant_id
                and result.get("available") is False
                and result.get("alternative_times")
            )
        ),
        None,
    )

    if not selected_result:
        return {
            "task_status": "no_alternatives"
        }

    print("\nRecovery found alternative times:")
    print(
        selected_result.get(
            "alternative_times"
        )
    )

    return {
        "availability_results": [selected_result],
        "task_status": "alternatives_found",
    }

# ---------------------------------------------------------
# OBSERVE TOOL RESULT
# ---------------------------------------------------------


def observe_tool_result(state: ResevaState):
    """
    Observe the result of the latest MCP tool execution.

    Operational tool failures are marked as tool_error and
    increment retry_count so the agent can decide whether to
    retry or adapt.

    Successful tools preserve the existing business workflow
    state instead of overwriting states such as:

        processing
        availability_confirmed
        recovery_needed
        booking_approved
        completed
    """

    tool_messages = [
        message
        for message in state["messages"]
        if getattr(message, "name", None)
    ]

    if not tool_messages:
        return {}

    latest_tool = tool_messages[-1]

    tool_name = getattr(
        latest_tool,
        "name",
        None,
    )

    tool_status = getattr(
        latest_tool,
        "status",
        None,
    )

    tool_content = getattr(
        latest_tool,
        "content",
        None,
    )

    retry_count = state.get(
        "retry_count",
        0,
    )

    current_task_status = state.get(
        "task_status",
        "processing",
    )

    result = {
        "last_tool": tool_name,

        "last_tool_result": {
            "status": tool_status,
            "content": tool_content,
        },

        "current_step": tool_name,

        # Always preserve the current retry count on
        # successful execution.
        "retry_count": retry_count,

        # Always return task_status so callers/tests can
        # inspect the current workflow state.
        "task_status": current_task_status,
    }

    # ---------------------------------------------------------
    # TOOL FAILURE
    # ---------------------------------------------------------

    if tool_status == "error":

        result["retry_count"] = (
            retry_count + 1
        )

        result["task_status"] = (
            "tool_error"
        )

    return result




# ---------------------------------------------------------
# ROUTE AFTER TOOLS
# ---------------------------------------------------------

def route_after_agent(state: ResevaState):
    """
    Decide what the graph should do after the reasoning node.

    Claude tool calls always take priority.

    Deterministic reservation mutations are controlled by
    the graph and never performed directly by Claude.
    """

    latest_message = state["messages"][-1]

    # ---------------------------------------------------------
    # CLAUDE TOOL CALLS
    # ---------------------------------------------------------

    if latest_message.tool_calls:
        return "tools"

    # ---------------------------------------------------------
    # CANCELLATION
    # ---------------------------------------------------------

    if state.get("cancellation_requested") is True:
        return "cancellation_lookup"

    # ---------------------------------------------------------
    # MODIFICATION
    # ---------------------------------------------------------

    if state.get("modification_requested") is True:
        return "modification_lookup"

    # ---------------------------------------------------------
    # RECOVERY
    # ---------------------------------------------------------

    if state.get("task_status") == "recovery_needed":
        return "alternative_times"

    # ---------------------------------------------------------
    # BOOKING
    # ---------------------------------------------------------
    #
    # This is deterministic.
    #
    # If the user explicitly requested a booking and all
    # required information exists, stop Claude from simply
    # replying "I'll book it" and enter the real booking
    # approval workflow.
    # ---------------------------------------------------------

    if (
        state.get("booking_requested") is True
        and state.get("selected_restaurant_id")
        and state.get("date")
        and state.get("time")
        and state.get("party_size")
    ):
        return "booking_email"

    # ---------------------------------------------------------
    # WAIT FOR USER
    # ---------------------------------------------------------

    return END


# ---------------------------------------------------------
# MODIFICATION LOOKUP
# ---------------------------------------------------------

async def modification_lookup_node(state: ResevaState):
    """Retrieve the existing reservation and prepare new values.

    This node only reads the reservation. It does not modify it.
    """

    reservation_id = state.get("reservation_id_to_modify")

    if not reservation_id:
        reservation_id = state.get("reservation_id")

    if not reservation_id:
        return {
            "reservation_lookup": None,
            "modification_requested": False,
            "task_status": "modification_missing_id",
        }

    result = await get_reservation.ainvoke({
        "reservation_id": reservation_id,
    })

    if not result.get("success") or not result.get("reservation"):
        return {
            "reservation_lookup": None,
            "modification_requested": False,
            "task_status": "modification_reservation_not_found",
        }

    reservation = result["reservation"]

    # Preserve information already stored in the graph state,
    # especially the customer's email address.
    previous_lookup = dict(state.get("reservation_lookup") or {})

    merged_lookup = {
        **previous_lookup,
        **reservation,
    }

    if merged_lookup.get("status") == "cancelled":
        return {
            "reservation_lookup": merged_lookup,
            "reservation_status": "cancelled",
            "modification_requested": False,
            "task_status": "modification_not_allowed",
        }

    # If the user changed only one field, preserve the other
    # existing reservation values.
    new_date = (
        state.get("modification_date")
        or merged_lookup.get("date")
    )

    new_time = (
        state.get("modification_time")
        or merged_lookup.get("time")
    )

    new_party_size = (
        state.get("modification_party_size")
        or merged_lookup.get("party_size")
    )

    if not all([new_date, new_time, new_party_size]):
        return {
            "reservation_lookup": merged_lookup,
            "reservation_status": merged_lookup.get("status"),
            "modification_requested": False,
            "task_status": "modification_missing_details",
        }

    return {
        "reservation_id_to_modify": reservation_id,
        "reservation_lookup": merged_lookup,
        "reservation_status": merged_lookup.get("status"),
        "modification_date": new_date,
        "modification_time": new_time,
        "modification_party_size": new_party_size,
        "task_status": "modification_checking_availability",
    }

async def modification_availability_node(state: ResevaState):
    """Check the requested new reservation details before mutation."""

    reservation = state.get("reservation_lookup") or {}
    restaurant_id = reservation.get("restaurant_id")
    date = state.get("modification_date")
    time = state.get("modification_time")
    party_size = state.get("modification_party_size")

    if not all([restaurant_id, date, time, party_size]):
        return {
            "modification_requested": False,
            "task_status": "modification_missing_details",
        }

    result = await check_availability.ainvoke({
        "restaurant_id": restaurant_id,
        "date": date,
        "time": time,
        "party_size": party_size,
    })

    if not result.get("available"):
        return {
            "availability_results": [result],
            "modification_requested": False,
            "task_status": "modification_unavailable",
        }

    return {
        "availability_results": [result],
        "task_status": "modification_ready",
    }


def route_after_modification_lookup(state: ResevaState):
    status = state.get("task_status")

    if status == "modification_checking_availability":
        return "modification_availability"

    return "agent"


# ---------------------------------------------------------
# MODIFICATION APPROVAL
# ---------------------------------------------------------

def modification_approval(state: ResevaState):
    """Pause before changing an existing reservation."""

    reservation = state.get("reservation_lookup") or {}
    restaurant_name = reservation.get("restaurant_name", "the restaurant")

    approval = interrupt({
        "type": "modification_confirmation",
        "reservation_id": reservation.get("reservation_id"),
        "restaurant": restaurant_name,
        "old_date": reservation.get("date"),
        "old_time": reservation.get("time"),
        "old_party_size": reservation.get("party_size"),
        "new_date": state.get("modification_date"),
        "new_time": state.get("modification_time"),
        "new_party_size": state.get("modification_party_size"),
        "message": (
            f"You're about to change your reservation at {restaurant_name} "
            f"from {reservation.get('date')} at {reservation.get('time')} "
            f"for {reservation.get('party_size')} people to "
            f"{state.get('modification_date')} at "
            f"{state.get('modification_time')} for "
            f"{state.get('modification_party_size')} people. "
            "Do you want me to proceed?"
        ),
    })

    if _is_approved(approval):
        return {"task_status": "modification_approved"}

    return {
        "task_status": "modification_rejected",
        "modification_requested": False,
    }


def route_after_modification_availability(state: ResevaState):
    if state.get("task_status") == "modification_ready":
        return "modification_approval"
    return "agent"


def route_after_modification_approval(state):
    if state.get("task_status") == "modification_approved":
        if _get_customer_email(state):
            return "modify_reservation"

        return "modification_email"

    return "end"

def route_after_modification_email(state):
    if state.get("task_status") in (
        "modification_email_available",
        "modification_email_collected",
    ):
        return "modify_reservation"

    return "end"

# ---------------------------------------------------------
# MODIFY RESERVATION
# ---------------------------------------------------------

async def modify_reservation_node(state: ResevaState):
    """Perform the actual modification after human approval."""

    reservation_id = state.get("reservation_id_to_modify")
    date = state.get("modification_date")
    time = state.get("modification_time")
    party_size = state.get("modification_party_size")

    if not all([reservation_id, date, time, party_size]):
        return {
            "reservation_status": "failed",
            "modification_requested": False,
            "task_status": "modification_failed",
        }

    result = await modify_reservation.ainvoke({
        "reservation_id": reservation_id,
        "date": date,
        "time": time,
        "party_size": party_size,
    })

    if not result.get("success"):
        return {
            "reservation_status": "failed",
            "modification_requested": False,
            "task_status": "modification_failed",
        }

    reservation = result.get("reservation", {})

    # Preserve information from the original reservation,
    # especially the customer's email address, while updating
    # it with the modified reservation returned by the provider.
    previous_lookup = dict(state.get("reservation_lookup") or {})

    merged_lookup = {
        **previous_lookup,
        **reservation,
    }

    return {
        "reservation_id": merged_lookup.get(
            "reservation_id",
            reservation_id,
        ),
        "reservation_status": merged_lookup.get(
            "status",
            "confirmed",
        ),
        "reservation_lookup": merged_lookup,
        "date": merged_lookup.get(
            "date",
            date,
        ),
        "time": merged_lookup.get(
            "time",
            time,
        ),
        "party_size": merged_lookup.get(
            "party_size",
            party_size,
        ),
        "selected_restaurant_id": (
            state.get("selected_restaurant_id")
            or merged_lookup.get("restaurant_id")
        ),
        "task_status": "completed",
        "modification_requested": False,
    }


# ---------------------------------------------------------
# MODIFICATION EMAIL REQUEST
# ---------------------------------------------------------

def modification_email_request(state: ResevaState):
    """Ask for the customer's email when it is not already available."""

    email = _get_customer_email(state)

    if email:
        return {
            "task_status": "modification_email_available",
        }

    email_input = interrupt({
        "type": "modification_email",
        "message": (
            "Please provide your email address so I can send "
            "your updated reservation confirmation."
        ),
    })

    if isinstance(email_input, str) and _valid_email(email_input):
        return {
            **_store_customer_email(
                state,
                email_input.strip(),
            ),
            "task_status": "modification_email_collected",
        }

    return {
        "task_status": "modification_email_invalid",
    }


# ---------------------------------------------------------
# MODIFICATION CONFIRMATION EMAIL
# ---------------------------------------------------------

async def send_modification_confirmation_email(state: ResevaState):
    """Send modification confirmation after the reservation is successfully modified."""

    if state.get("reservation_status") != "confirmed":
        return {
            "email_status": "not_sent",
            "task_status": state.get("task_status", "modification_failed"),
        }

    email = _get_customer_email(state)

    if not email:
        return {
            "email_status": "not_sent",
            "task_status": "modification_confirmed_email_missing",
        }

    reservation = state.get("reservation_lookup") or {}

    restaurant = reservation.get(
        "restaurant_name",
        "the restaurant",
    )

    reservation_id = reservation.get(
        "reservation_id",
        state.get("reservation_id"),
    )

    date = state.get("date")
    time = state.get("time")
    party_size = state.get("party_size")

    result = _send_resend_email(
        to_email=email,
        subject=f"Reseva modification confirmation - {restaurant}",
        text_body=(
            "Your Reseva reservation has been successfully modified.\n\n"
            f"Restaurant: {restaurant}\n"
            f"Date: {date}\n"
            f"Time: {time}\n"
            f"Party size: {party_size}\n"
            f"Reservation ID: {reservation_id}\n"
        ),
        html_body=(
            "<h2>Your Reseva reservation has been successfully modified</h2>"
            f"<p><strong>Restaurant:</strong> {restaurant}</p>"
            f"<p><strong>Date:</strong> {date}</p>"
            f"<p><strong>Time:</strong> {time}</p>"
            f"<p><strong>Party size:</strong> {party_size}</p>"
            f"<p><strong>Reservation ID:</strong> {reservation_id}</p>"
        ),
    )

    return {
        "email_status": "sent" if result.get("success") else "failed",
        "email_result": result,
        "task_status": "completed",
    }

# ---------------------------------------------------------
# MODIFICATION CONFIRMATION MESSAGE
# ---------------------------------------------------------

def modification_confirmation_message(state: ResevaState):
    """Create the final user-facing modification confirmation."""

    restaurant_names = {
        "rest-001": "Bella Italia Mayfair",
        "rest-002": "La Tavola",
    }

    restaurant_id = state.get("selected_restaurant_id")
    restaurant_name = restaurant_names.get(
        restaurant_id,
        "the selected restaurant",
    )

    reservation_id = state.get("reservation_id")
    date = state.get("date")
    time = state.get("time")
    party_size = state.get("party_size")

    email_line = (
        "Modification email sent."
        if state.get("email_status") == "sent"
        else "The reservation was modified, but the modification email could not be sent."
    )

    message = (
        "Your reservation has been successfully modified!\n\n"
        f"Restaurant: {restaurant_name}\n"
        f"Date: {date}\n"
        f"Time: {time}\n"
        f"Party size: {party_size}\n"
        f"Reservation ID: {reservation_id}\n"
        f"{email_line}"
    )

    return {
        "messages": [
            {
                "role": "assistant",
                "content": message,
            }
        ]
    }


# ---------------------------------------------------------
# CANCELLATION LOOKUP
# ---------------------------------------------------------

async def cancellation_lookup_node(state: ResevaState):
    """Retrieve the reservation that the user wants to cancel.

    This node only looks up the reservation. It does not cancel it.
    """

    reservation_id = state.get("reservation_id_to_modify")

    if not reservation_id:
        return {
            "reservation_lookup": None,
            "task_status": "cancellation_missing_id",
        }

    print("\nLooking up reservation for cancellation:")
    print("Reservation ID:", reservation_id)

    result = await get_reservation.ainvoke({
        "reservation_id": reservation_id,
    })

    if not result.get("success") or not result.get("reservation"):
        return {
            "reservation_lookup": None,
            "task_status": "cancellation_reservation_not_found",
        }

    reservation = result["reservation"]

    if reservation.get("status") == "cancelled":
        return {
            "reservation_lookup": reservation,
            "reservation_status": "cancelled",
            "task_status": "already_cancelled",
        }

    return {
        "reservation_lookup": reservation,
        "reservation_status": reservation.get("status"),
        "task_status": "cancellation_ready",
    }


def route_after_cancellation_lookup(state: ResevaState):
    """Route a successful lookup to human approval."""

    if state.get("task_status") == "cancellation_ready":
        return "cancellation_email"

    return "agent"


# ---------------------------------------------------------
# CANCELLATION APPROVAL
# ---------------------------------------------------------

def cancellation_approval(state: ResevaState):
    """Pause and obtain explicit approval before cancellation."""

    reservation = state.get("reservation_lookup")

    if not reservation:
        return {
            "task_status": "cancellation_failed",
        }

    restaurant_name = reservation.get(
        "restaurant_name",
        "the restaurant",
    )

    approval = interrupt({
        "type": "cancellation_confirmation",
        "reservation_id": reservation.get("reservation_id"),
        "restaurant": restaurant_name,
        "date": reservation.get("date"),
        "time": reservation.get("time"),
        "party_size": reservation.get("party_size"),
        "message": (
            f"You're about to cancel your reservation at "
            f"{restaurant_name} for {reservation.get('party_size')} people "
            f"on {reservation.get('date')} at {reservation.get('time')}. "
            "Do you want me to proceed?"
        ),
    })

    if _is_approved(approval):
        return {
            "task_status": "cancellation_approved",
    }

    return {
        "task_status": "cancellation_rejected",
        "cancellation_requested": False,
    }


def route_after_cancellation_approval(state: ResevaState):
    """Continue to cancellation only after explicit approval."""

    if state.get("task_status") == "cancellation_approved":
        return "cancel_reservation"

    return "end"


# ---------------------------------------------------------
# CANCEL RESERVATION
# ---------------------------------------------------------

async def cancel_reservation_node(state: ResevaState):
    """Perform the actual cancellation after human approval."""

    reservation_id = state.get("reservation_id_to_modify")

    if not reservation_id:
        return {
            "reservation_status": "failed",
            "task_status": "cancellation_failed",
        }

    result = await cancel_reservation.ainvoke({
        "reservation_id": reservation_id,
    })

    if not result.get("success"):
        return {
            "reservation_status": "failed",
            "task_status": "cancellation_failed",
        }

    reservation = result.get("reservation", {})

    # Preserve information collected before cancellation,
    # especially the customer's email address.
    previous_lookup = dict(state.get("reservation_lookup") or {})

    merged_lookup = {
        **previous_lookup,
        **reservation,
    }

    return {
        "reservation_id": reservation.get(
            "reservation_id",
            reservation_id,
        ),
        "reservation_status": reservation.get(
            "status",
            "cancelled",
        ),
        "reservation_lookup": merged_lookup,
        "task_status": "completed",
        "cancellation_requested": False,
    }

# ---------------------------------------------------------
# CANCELLATION CONFIRMATION EMAIL
# ---------------------------------------------------------

async def send_cancellation_confirmation_email(state: ResevaState):
    """Send cancellation confirmation after the cancellation succeeds."""
    if state.get("reservation_status") != "cancelled":
        return {"task_status": state.get("task_status", "cancellation_failed")}
    email = _get_customer_email(state)
    if not email:
        return {"email_status": "not_sent", "task_status": "cancellation_confirmed_email_missing"}
    reservation = state.get("reservation_lookup") or {}
    restaurant = reservation.get("restaurant_name", "the restaurant")
    reservation_id = reservation.get("reservation_id", state.get("reservation_id"))
    date = reservation.get("date", state.get("date"))
    time = reservation.get("time", state.get("time"))
    party_size = reservation.get("party_size", state.get("party_size"))
    result = _send_resend_email(
        to_email=email,
        subject=f"Reseva cancellation confirmation - {restaurant}",
        text_body=(f"Your Reseva reservation has been cancelled.\n\nRestaurant: {restaurant}\nDate: {date}\nTime: {time}\nParty size: {party_size}\nReservation ID: {reservation_id}\n"),
        html_body=(f"<h2>Your Reseva reservation has been cancelled</h2><p><strong>Restaurant:</strong> {restaurant}</p><p><strong>Date:</strong> {date}</p><p><strong>Time:</strong> {time}</p><p><strong>Party size:</strong> {party_size}</p><p><strong>Reservation ID:</strong> {reservation_id}</p>"),
    )
    return {"email_status": "sent" if result.get("success") else "failed", "email_result": result, "task_status": "completed"}


# ---------------------------------------------------------
# CANCELLATION CONFIRMATION MESSAGE
# ---------------------------------------------------------

def cancellation_confirmation_message(state: ResevaState):
    """Create the final user-facing cancellation confirmation."""

    reservation = state.get("reservation_lookup") or {}

    restaurant_name = reservation.get("restaurant_name") or "the restaurant"
    reservation_id = reservation.get("reservation_id") or state.get("reservation_id")
    date = reservation.get("date") or state.get("date")
    time = reservation.get("time") or state.get("time")
    party_size = reservation.get("party_size") or state.get("party_size")

    email_line = (
        "Cancellation email sent."
        if state.get("email_status") == "sent"
        else "The reservation was cancelled, but the cancellation email could not be sent."
    )

    message = (
        "Your reservation has been successfully cancelled!\n\n"
        f"Restaurant: {restaurant_name}\n"
        f"Date: {date}\n"
        f"Time: {time}\n"
        f"Party size: {party_size}\n"
        f"Reservation ID: {reservation_id}\n"
        f"{email_line}"
    )

    return {
        "messages": [
            {
                "role": "assistant",
                "content": message,
            }
        ]
    }


# ---------------------------------------------------------
# BOOKING APPROVAL
# ---------------------------------------------------------

def booking_approval(state: ResevaState):
    """
    Pause Reseva and ask the user to approve the
    selected reservation.
    """

    restaurant_id = state.get(
        "selected_restaurant_id"
    )

    restaurant_names = {
        "rest-001": "Bella Italia Mayfair",
        "rest-002": "La Tavola",
    }

    restaurant_name = restaurant_names.get(
        restaurant_id,
        "the selected restaurant",
    )

    approval = interrupt({
        "type": "booking_confirmation",
        "restaurant_id": restaurant_id,
        "restaurant": restaurant_name,
        "date": state.get("date"),
        "time": state.get("time"),
        "party_size": state.get("party_size"),
        "message": (
            f"You're about to book {restaurant_name} "
            f"for {state.get('party_size')} people "
            f"on {state.get('date')} at {state.get('time')}. "
            "Do you want me to proceed?"
        ),
    })

    if _is_approved(approval):
    
        return {
            "task_status": "booking_approved",
        }

    return {
        "task_status": "booking_rejected",
        "booking_requested": False,
    }

def route_after_booking_approval(state: ResevaState):
    """
    Decide whether to collect the customer's email after human approval.

    Only an explicit approval is allowed to continue to the email
    collection step. Any other outcome stops the booking flow.
    """
    if state.get("task_status") == "booking_approved":
        return "booking_email"

    return "end"


# ---------------------------------------------------------
# CREATE RESERVATION
# ---------------------------------------------------------

async def create_reservation_node(state: ResevaState):

    restaurant_id = state.get(
        "selected_restaurant_id"
    )

    date = state.get("date")
    time = state.get("time")
    party_size = state.get("party_size")

    if not restaurant_id:
        return {
            "reservation_status": "failed",
            "task_status": "error",
        }

    if not date or not time or not party_size:
        return {
            "reservation_status": "failed",
            "task_status": "error",
        }

    booking_result = await create_reservation.ainvoke(
        {
            "restaurant_id": restaurant_id,
            "date": date,
            "time": time,
            "party_size": party_size,
        }
    )

    if not booking_result.get("success"):
        return {
            "reservation_status": "failed",
            "task_status": "booking_failed",
        }

    db = SessionLocal()

    try:

        reservation = save_reservation(
            db,
            booking_result,
        )

        return {
            "reservation_id": reservation.reservation_id,
            "reservation_status": reservation.status,
            "task_status": "completed",
        }

    finally:
        db.close()

# ---------------------------------------------------------
# BOOKING CONFIRMATION EMAIL
# ---------------------------------------------------------

async def send_booking_confirmation_email(state: ResevaState):
    """Send booking confirmation after the reservation succeeds."""
    if state.get("reservation_status") != "confirmed":
        return {"task_status": state.get("task_status", "booking_failed")}
    email = _get_customer_email(state)
    if not email:
        return {"email_status": "not_sent", "task_status": "booking_confirmed_email_missing"}
    names = {"rest-001": "Bella Italia Mayfair", "rest-002": "La Tavola", "rest-003": "The Mayfair Grill", "rest-004": "Sushi House Mayfair"}
    restaurant = names.get(state.get("selected_restaurant_id"), "the selected restaurant")
    reservation_id = state.get("reservation_id")
    date, time, party_size = state.get("date"), state.get("time"), state.get("party_size")
    result = _send_resend_email(
        to_email=email,
        subject=f"Reseva booking confirmation - {restaurant}",
        text_body=(f"Your Reseva reservation is confirmed.\n\nRestaurant: {restaurant}\nDate: {date}\nTime: {time}\nParty size: {party_size}\nReservation ID: {reservation_id}\n"),
        html_body=(f"<h2>Your Reseva reservation is confirmed</h2><p><strong>Restaurant:</strong> {restaurant}</p><p><strong>Date:</strong> {date}</p><p><strong>Time:</strong> {time}</p><p><strong>Party size:</strong> {party_size}</p><p><strong>Reservation ID:</strong> {reservation_id}</p>"),
    )
    return {"email_status": "sent" if result.get("success") else "failed", "email_result": result, "task_status": "completed"}


# ---------------------------------------------------------
# BOOKING CONFIRMATION MESSAGE
# ---------------------------------------------------------

def booking_confirmation_message(state: ResevaState):
    """Create the final user-facing booking confirmation."""

    restaurant_names = {
        "rest-001": "Bella Italia Mayfair",
        "rest-002": "La Tavola",
    }

    restaurant_id = state.get("selected_restaurant_id")
    restaurant_name = restaurant_names.get(
        restaurant_id,
        "the selected restaurant",
    )

    reservation_id = state.get("reservation_id")
    date = state.get("date")
    time = state.get("time")
    party_size = state.get("party_size")
    status = state.get("reservation_status")

    if status == "confirmed":
        email_line = (
            "Confirmation email sent."
            if state.get("email_status") == "sent"
            else "The reservation was confirmed, but the confirmation email could not be sent."
        )
        message = (
            "Your reservation is confirmed!\n\n"
            f"Restaurant: {restaurant_name}\n"
            f"Date: {date}\n"
            f"Time: {time}\n"
            f"Party size: {party_size}\n"
            f"Reservation ID: {reservation_id}\n"
            f"{email_line}"
        )
    else:
        message = (
            "I couldn't complete the reservation.\n\n"
            f"Restaurant: {restaurant_name}\n"
            f"Date: {date}\n"
            f"Time: {time}\n"
            f"Party size: {party_size}\n"
            f"Status: {status}"
        )

    return {
        "messages": [
            {
                "role": "assistant",
                "content": message,
            }
        ]
    }


# ---------------------------------------------------------
# MAIN RESEVA AGENT
# ---------------------------------------------------------

def reseva_node(state: ResevaState):
    """
    Main Reseva reasoning node.
    """

    prompt = f"""
You are Reseva, an autonomous AI restaurant reservation agent.

Your goal is to help the user find and eventually book a restaurant.

Current reservation state:

Location: {state.get("location")}
Cuisine: {state.get("cuisine")}
Reservation date: {state.get("date")}
Reservation time: {state.get("time")}
Party size: {state.get("party_size")}
Budget: {state.get("budget")}

Selected restaurant ID:
{state.get("selected_restaurant_id")}

Available restaurants:
{state.get("available_restaurants")}

Availability results:
{state.get("availability_results")}

Booking requested:
{state.get("booking_requested")}

Reservation ID:
{state.get("reservation_id")}

Reservation status:
{state.get("reservation_status")}

Cancellation requested:
{state.get("cancellation_requested")}

Reservation ID to modify/cancel:
{state.get("reservation_id_to_modify")}

Task status:
{state.get("task_status")}

Current execution plan:
{state.get("plan", [])}

Current execution step:
{state.get("current_step")}

Last MCP tool:
{state.get("last_tool")}

Last MCP tool result:
{state.get("last_tool_result")}

Retry count:
{state.get("retry_count", 0)}


IMPORTANT:

The state values above are authoritative.

If the state contains a reservation date,
do NOT ask the user for the date again.

If the state contains a reservation time,
do NOT ask the user for the time again.

If the state contains a party size,
do NOT ask for it again unless the user changes it.

Relative dates and times have already been converted
by the extraction system.

AUTONOMOUS EXECUTION RULES:

The execution plan is a working plan, not a rigid script.

Use the current state and the latest tool result to decide
the next appropriate action.

After each tool result:

1. Observe what happened.
2. Compare the result with the current goal.
3. Decide whether another tool is required.
4. If another tool is required, use the appropriate MCP tool.
5. If the task cannot continue, explain what information
   is missing or what went wrong.
6. Do not repeat a failed tool call unnecessarily.
7. Adapt the plan when circumstances change.


MODIFICATION SAFETY RULE:

The modify_reservation tool changes an existing reservation.
NEVER call modify_reservation automatically.
The graph controls the mutation and requires explicit user approval.
Before modification, the graph must check availability for the new
date, time and party size. Do not claim the reservation was changed
unless modify_reservation actually succeeds.

BOOKING SAFETY RULE:

The create_reservation tool creates an actual reservation.

NEVER call create_reservation automatically.

The graph controls actual reservation creation.

Before a reservation can be created, Reseva must obtain
explicit confirmation from the user.


FOLLOW THIS PROCESS:

1. If you need restaurants matching the user's requirements,
   use search_restaurants.

2. Once restaurants are found and the user has provided
   a date, time and party size, check availability.

3. Store and use the availability results.

4. If a restaurant is unavailable, consider another suitable
   restaurant from the available search results.

5. If exactly one suitable restaurant is available,
   clearly present that option to the user.

6. If multiple restaurants are available,
   ask the user which restaurant they want.

7. If the user says "book it", use the selected restaurant
   already stored in the state if one exists.

8. Never invent a restaurant ID.

9. Only use restaurant IDs returned by search_restaurants.

10. Do not claim that a reservation has been made unless
    create_reservation actually returns success.

11. If required information is missing, ask the user for it.

12. Continue reasoning until you can provide the appropriate
    next step.

13. When calling check_availability, use the exact values
    from the current reservation state.

14. Date must always be in YYYY-MM-DD format.

15. Time must always be in HH:MM 24-hour format.

16. Never pass relative values such as "tomorrow" or "7pm"
    to a tool.

17. If the reservation date, time and party size are present,
    check availability when appropriate.

18. If the user explicitly requests a booking but has not
    selected a restaurant, do not create a reservation.

19. Actual reservation creation is controlled by the graph
    and requires explicit approval.

20. Never state that a booking is confirmed before the
    reservation creation step succeeds.

21. If the requested time is unavailable, Reseva will search
    for alternative times.

22. When alternative times are available, clearly present
    them to the user.

23. Do not automatically change the user's requested time.

24. Wait for the user to choose an alternative time.

25. If the user selects an alternative time, use that new
    time and check its availability before booking.

26. If the state contains task_status = "alternatives_found",
    present the alternative times to the user rather than
    repeating the same availability search.

27. Do not call get_alternative_times repeatedly if
    alternative times have already been found.

28. When the user selects a new alternative time for an
    already-selected restaurant, the graph will perform a
    fresh availability check before continuing.

29. If the user wants to cancel an existing reservation,
    do not cancel it automatically. The graph will look up
    the reservation and request explicit confirmation.

30. Never claim a reservation has been cancelled unless
    the cancellation tool actually returns success.

31. If the user has not provided a reservation ID and no
    reservation ID exists in state, ask the user for it.
"""

    messages = [
        SystemMessage(content=prompt),
        *state["messages"],
    ]

    response = llm_with_tools.invoke(messages)

    print("\nClaude:")
    print(response.content)

    if response.tool_calls:
        print("\nClaude requested tool:")
        print(response.tool_calls)

    # Preserve important workflow states that were set by
    # deterministic graph nodes.
    current_task_status = state.get(
        "task_status"
    )

    if current_task_status in {
        "recovery_needed",
        "alternatives_found",
    }:
        task_status = current_task_status
    else:
        task_status = "processing"

    # ---------------------------------------------------------
    # UPDATE EXECUTION STEP
    # ---------------------------------------------------------

    current_step = state.get("current_step")

    if state.get("booking_requested") is True:
        current_step = "Request explicit booking approval"

    elif task_status == "availability_confirmed":
        current_step = "Present suitable options to the user"

    elif task_status == "alternatives_found":
        current_step = "Present alternative times to the user"

    elif task_status == "waiting_for_selection":
        current_step = "Wait for restaurant and time selection"

    return {
        "messages": [response],
        "task_status": task_status,
        "current_step": current_step,
    }


# ---------------------------------------------------------
# ROUTE AFTER AGENT
# ---------------------------------------------------------

def route_after_agent(state: ResevaState):
    """
    Decide what the graph should do after the reasoning node.

    Claude tool calls always take priority.

    A booking approval is only allowed when the selected
    restaurant has been explicitly confirmed available for
    the current date and time.
    """

    latest_message = state["messages"][-1]

    # ---------------------------------------------------------
    # 1. Claude tool calls always take priority
    # ---------------------------------------------------------
    if latest_message.tool_calls:
        return "tools"

    # ---------------------------------------------------------
    # 2. Cancellation
    # ---------------------------------------------------------
    if state.get("cancellation_requested") is True:
        return "cancellation_lookup"

    # ---------------------------------------------------------
    # 3. Modification
    # ---------------------------------------------------------
    if state.get("modification_requested") is True:
        return "modification_lookup"

    # ---------------------------------------------------------
    # 4. Recovery
    # ---------------------------------------------------------
    if state.get("task_status") == "recovery_needed":
        return "alternative_times"

    # ---------------------------------------------------------
    # 5. Booking approval
    # ---------------------------------------------------------
    #
    # NEVER approve a booking merely because the user requested
    # one. The selected restaurant must have a confirmed
    # availability result for the exact date/time.
    #
    if (
        state.get("booking_requested") is True
        and state.get("selected_restaurant_id")
        and state.get("date")
        and state.get("time")
        and state.get("party_size")
    ):
        selected_restaurant_id = state.get(
            "selected_restaurant_id"
        )

        date = state.get("date")
        time = state.get("time")

        # Find the latest availability result for the
        # currently selected restaurant.
        latest_result = None

        for result in reversed(
            state.get("availability_results", [])
        ):
            if (
                result.get("restaurant_id")
                == selected_restaurant_id
                and result.get("date") == date
                and result.get("time") == time
            ):
                latest_result = result
                break

        # Only allow booking approval when availability is
        # explicitly confirmed.
        if (
            latest_result is not None
            and latest_result.get("available") is True
        ):
            return "booking_approval"

        # If availability has not been checked for the exact
        # restaurant/date/time, perform a deterministic check.
        if latest_result is None:
            return "check_selected_restaurant"

        # If the exact requested time was checked and is
        # unavailable, send the flow into recovery.
        if latest_result.get("available") is False:
            return "alternative_times"

    # ---------------------------------------------------------
    # 6. Otherwise wait for the next user message
    # ---------------------------------------------------------
    return END


# ---------------------------------------------------------
# ROUTE AFTER TOOLS
# ---------------------------------------------------------

def route_after_tools(state: ResevaState):
    """
    Decide what should happen after MCP tools finish.

    Operational MCP failures are sent back to the agent so it can
    decide whether to retry, change strategy, or continue.
    """

    tool_messages = [
        message
        for message in state["messages"]
        if getattr(message, "name", None)
    ]

    if not tool_messages:
        return "agent"

    latest_tool = tool_messages[-1]

    # Operational MCP/tool failure.
    if getattr(latest_tool, "status", None) == "error":
        if state.get("retry_count", 0) >= 3:
            return END

        return "agent"

    # Normal successful tool routing.
    if latest_tool.name == "search_restaurants":
        return "store_search_results"

    if latest_tool.name == "check_availability":
        return "store_availability_results"

    if latest_tool.name == "get_alternative_times":
        return "agent"

    return "agent"


# ---------------------------------------------------------
# BUILD GRAPH
# ---------------------------------------------------------

builder = StateGraph(ResevaState)


# ---------------------------------------------------------
# NODES
# ---------------------------------------------------------

builder.add_node(
    "extract_state",
    extract_state,
)

builder.add_node(
    "planner",
    create_agent_plan,
)

builder.add_node(
    "agent",
    reseva_node,
)


def handle_tool_error(error: Exception) -> str:
    """
    Convert operational tool failures into a ToolMessage
    instead of allowing the exception to terminate the graph.
    """
    return f"Tool execution failed: {error}"


builder.add_node(
    "tools",
    ToolNode(
        tools,
        handle_tool_errors=handle_tool_error,
    ),
)


builder.add_node(
    "observe_tool_result",
    observe_tool_result,
)

builder.add_node(
    "store_search_results",
    store_search_results,
)

builder.add_node(
    "store_availability_results",
    store_availability_results,
)

builder.add_node(
    "check_selected_restaurant",
    check_selected_restaurant_node,
)

builder.add_node(
    "alternative_times",
    alternative_times_node,
)

builder.add_node(
    "booking_email",
    booking_email_request,
)

builder.add_node(
    "booking_approval",
    booking_approval,
)

builder.add_node(
    "create_reservation",
    create_reservation_node,
)

builder.add_node(
    "send_booking_confirmation_email",
    send_booking_confirmation_email,
)

builder.add_node(
    "booking_confirmation_message",
    booking_confirmation_message,
)

builder.add_node(
    "modification_lookup",
    modification_lookup_node,
)

builder.add_node(
    "modification_availability",
    modification_availability_node,
)

builder.add_node(
    "modification_approval",
    modification_approval,
)

builder.add_node(
    "modify_reservation",
    modify_reservation_node,
)

builder.add_node(
    "modification_email",
    modification_email_request,
)

builder.add_node(
    "send_modification_confirmation_email",
    send_modification_confirmation_email,
)

builder.add_node(
    "modification_confirmation_message",
    modification_confirmation_message,
)

builder.add_node(
    "cancellation_lookup",
    cancellation_lookup_node,
)

builder.add_node(
    "cancellation_email",
    cancellation_email_request,
)

builder.add_node(
    "cancellation_approval",
    cancellation_approval,
)

builder.add_node(
    "cancel_reservation",
    cancel_reservation_node,
)

builder.add_node(
    "send_cancellation_confirmation_email",
    send_cancellation_confirmation_email,
)

builder.add_node(
    "cancellation_confirmation_message",
    cancellation_confirmation_message,
)


# ---------------------------------------------------------
# INITIAL FLOW
# ---------------------------------------------------------

builder.add_edge(
    START,
    "extract_state",
)


# ---------------------------------------------------------
# EXTRACT STATE → NEW TIME CHECK / AGENT
# ---------------------------------------------------------

builder.add_conditional_edges(
    "extract_state",
    route_after_extract_state,
    {
        "check_selected_restaurant": "check_selected_restaurant",
        "cancellation_lookup": "cancellation_lookup",
        "modification_lookup": "modification_lookup",
        "booking_email": "booking_email",
        "booking_approval": "booking_approval",
        "alternative_times": "alternative_times",
        "agent": "planner",
    },
)

# ---------------------------------------------------------
# PLANNER → AGENT
# ---------------------------------------------------------

builder.add_edge(
    "planner",
    "agent",
)


# ---------------------------------------------------------
# CANCELLATION LOOKUP → APPROVAL / AGENT
# ---------------------------------------------------------

builder.add_conditional_edges(
    "cancellation_lookup",
    route_after_cancellation_lookup,
    {
        "cancellation_email": "cancellation_email",
        "cancellation_approval": "cancellation_approval",
        "agent": "agent",
    },
)

# ---------------------------------------------------------
# MODIFICATION LOOKUP → AVAILABILITY / AGENT
# ---------------------------------------------------------

builder.add_conditional_edges(
    "modification_lookup",
    route_after_modification_lookup,
    {
        "modification_availability": "modification_availability",
        "agent": "agent",
    },
)

# ---------------------------------------------------------
# MODIFICATION AVAILABILITY → APPROVAL / AGENT
# ---------------------------------------------------------

builder.add_conditional_edges(
    "modification_availability",
    route_after_modification_availability,
    {
        "modification_approval": "modification_approval",
        "agent": "agent",
    },
)


# ---------------------------------------------------------
# NEW TIME CHECK → AGENT
# ---------------------------------------------------------

def route_after_selected_restaurant_check(state: ResevaState):
    """Route after a fresh availability check for the selected restaurant."""

    results = state.get("availability_results", [])

    if not results:
        return "agent"

    latest_result = results[-1]

    if (
        latest_result.get("available") is False
        and latest_result.get("alternative_times")
    ):
        return "alternative_times"

    return "agent"


builder.add_conditional_edges(
    "check_selected_restaurant",
    route_after_selected_restaurant_check,
    {
        "alternative_times": "alternative_times",
        "agent": "agent",
    },
)


# ---------------------------------------------------------
# AGENT → TOOL / END / APPROVAL
# ---------------------------------------------------------

builder.add_conditional_edges(
    "agent",
    route_after_agent,
)


# ---------------------------------------------------------
# TOOLS → STORE RESULTS
# ---------------------------------------------------------

builder.add_edge(
    "tools",
    "observe_tool_result",
)

builder.add_conditional_edges(
    "observe_tool_result",
    route_after_tools,
)


# ---------------------------------------------------------
# SEARCH RESULTS → AGENT
# ---------------------------------------------------------

builder.add_edge(
    "store_search_results",
    "agent",
)


# ---------------------------------------------------------
# AVAILABILITY RESULTS → RECOVERY / AGENT
# ---------------------------------------------------------

builder.add_conditional_edges(
    "store_availability_results",
    route_after_availability,
)


# ---------------------------------------------------------
# ALTERNATIVE TIMES → AGENT
# ---------------------------------------------------------

builder.add_edge(
    "alternative_times",
    "agent",
)


# ---------------------------------------------------------
# EMAIL → APPROVAL
# ---------------------------------------------------------

builder.add_conditional_edges(
    "booking_email",
    route_after_booking_email,
    {
        "create_reservation": "create_reservation",
        "end": END,
    },
)

builder.add_conditional_edges(
    "cancellation_email",
    route_after_cancellation_email,
    {"cancellation_approval": "cancellation_approval", "end": END},
)


# ---------------------------------------------------------
# APPROVAL → RESERVATION
# ---------------------------------------------------------

builder.add_conditional_edges(
    "booking_approval",
    route_after_booking_approval,
    {
        "booking_email": "booking_email",
        "end": END,
    },
)


# ---------------------------------------------------------
# CANCELLATION APPROVAL → CANCELLATION
# ---------------------------------------------------------

builder.add_conditional_edges(
    "modification_approval",
    route_after_modification_approval,
    {
        "modification_email": "modification_email",
        "modify_reservation": "modify_reservation",
        "end": END,
    },
)

builder.add_conditional_edges(
    "modification_email",
    route_after_modification_email,
    {
        "modify_reservation": "modify_reservation",
        "end": END,
    },
)

builder.add_conditional_edges(
    "cancellation_approval",
    route_after_cancellation_approval,
    {
        "cancel_reservation": "cancel_reservation",
        "end": END,
    },
)


# ---------------------------------------------------------
# RESERVATION → END
# ---------------------------------------------------------

builder.add_edge(
    "create_reservation",
    "send_booking_confirmation_email",
)

builder.add_edge(
    "send_booking_confirmation_email",
    "booking_confirmation_message",
)

builder.add_edge(
    "booking_confirmation_message",
    END,
)

builder.add_edge(
    "cancel_reservation",
    "send_cancellation_confirmation_email",
)

builder.add_edge(
    "send_cancellation_confirmation_email",
    "cancellation_confirmation_message",
)

builder.add_edge(
    "cancellation_confirmation_message",
    END,
)

builder.add_edge(
    "modify_reservation",
    "send_modification_confirmation_email",
)

builder.add_edge(
    "send_modification_confirmation_email",
    "modification_confirmation_message",
)

builder.add_edge(
    "modification_confirmation_message",
    END,
)


# ---------------------------------------------------------
# GRAPH BUILDER
# ---------------------------------------------------------

def build_graph(checkpointer):
    return builder.compile(
        checkpointer=checkpointer,
    )



