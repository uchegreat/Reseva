import uuid

from langchain_core.messages import HumanMessage

from agent.advanced_graph import (
    adapt_plan,
    evaluate_execution,
    route_after_evaluation,
)


def build_failed_execution_state():
    """
    Build a realistic state representing an unavailable
    requested reservation time.
    """

    original_request = (
        "Find me an Italian restaurant in Mayfair "
        "for 4 people at 19:00 and book it."
    )

    return {
        "messages": [
            HumanMessage(content=original_request)
        ],
        "user_id": str(uuid.uuid4()),
        "thread_id": str(uuid.uuid4()),
        "location": "Mayfair",
        "cuisine": "Italian",
        "date": "2026-09-25",
        "time": "19:00",
        "party_size": 4,
        "budget": None,
        "selected_restaurant_id": "rest-002",
        "available_restaurants": [
            {
                "id": "rest-002",
                "name": "La Tavola",
                "location": "Mayfair",
                "cuisine": "Italian",
            }
        ],
        "availability_results": [
            {
                "available": False,
                "restaurant_id": "rest-002",
                "date": "2026-09-25",
                "time": "19:00",
                "party_size": 4,
                "message": "No table is available at the requested time.",
                "alternative_times": [
                    "18:00",
                    "18:30",
                    "20:00",
                    "20:30",
                ],
            }
        ],
        "booking_requested": True,
        "reservation_id": None,
        "reservation_status": None,
        "task_status": "recovery_needed",
        "long_term_memories": {},
        "original_user_request": original_request,
        "plan_goal": (
            "Book an Italian restaurant in Mayfair "
            "for 4 people at 19:00."
        ),
        "plan_steps": [
            "Search for Italian restaurants in Mayfair.",
            "Check availability at 19:00.",
            "Book the selected restaurant if available.",
        ],
        "missing_information": [],
        "execution_summary": None,
        "goal_satisfied": False,
        "adaptation_needed": False,
        "next_action": None,
        "adaptation_count": 0,
    }


def test_evaluator_detects_failed_execution():
    """
    The evaluator should recognise that the requested time
    is unavailable and that another action is required.
    """

    state = build_failed_execution_state()

    result = evaluate_execution(state)

    assert result["goal_satisfied"] is False
    assert result["adaptation_needed"] is True
    assert result["next_action"] is not None


def test_failed_execution_routes_to_adaptation():
    """
    When execution fails and adaptation is required,
    the graph should route to the adaptive planner.
    """

    state = {
        "goal_satisfied": False,
        "adaptation_needed": True,
        "adaptation_count": 0,
    }

    result = route_after_evaluation(state)

    assert result == "adapt"


def test_adaptation_loop_is_protected():
    """
    Reseva should stop adapting after the configured maximum
    number of adaptive iterations.
    """

    state = {
        "goal_satisfied": False,
        "adaptation_needed": True,
        "adaptation_count": 2,
    }

    result = route_after_evaluation(state)

    assert result == "save_memory"


def test_adaptive_planner_changes_the_plan():
    """
    The adaptive planner should create a new plan using the
    failed execution result instead of blindly repeating
    the original plan.
    """

    state = build_failed_execution_state()

    state["execution_summary"] = (
        "The requested 19:00 reservation was unavailable. "
        "Alternative times are available."
    )

    state["adaptation_needed"] = True

    state["next_action"] = (
        "Use the available alternative times and determine "
        "the next step needed to continue the reservation."
    )

    result = adapt_plan(state)

    assert result["plan_goal"]
    assert result["plan_steps"]
    assert result["adaptation_count"] == 1

    new_plan = " ".join(result["plan_steps"]).lower()

    assert (
        "alternative" in new_plan
        or "availability" in new_plan
        or "time" in new_plan
        or "choose" in new_plan
    )


def test_original_request_is_preserved_after_adaptation():
    """
    Adaptive planning must never replace the original
    user request.
    """

    state = build_failed_execution_state()

    original_request = state["original_user_request"]

    state["execution_summary"] = (
        "19:00 was unavailable. Alternative times were found."
    )

    state["adaptation_needed"] = True

    state["next_action"] = (
        "Consider the available alternative reservation times."
    )

    adapt_plan(state)

    assert state["original_user_request"] == original_request

