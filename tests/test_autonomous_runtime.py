from langchain_core.messages import HumanMessage
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver

from agent.graph import build_graph


async def main():

    # ---------------------------------------------------------
    # CHECKPOINTER + GRAPH
    # ---------------------------------------------------------

    checkpointer = MemorySaver()
    graph = build_graph(checkpointer)

    # IMPORTANT:
    # All invocations use the SAME thread.
    thread_id = "runtime-test-resume-001"

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    # =========================================================
    # FIRST INVOCATION
    # =========================================================

    initial_state = {
        "messages": [
            {
                "role": "user",
                "content": (
                    "Find me an Italian restaurant in Mayfair "
                    "for 2 people tomorrow at 7pm."
                ),
            }
        ],

        "user_id": "runtime-user-001",
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

    print("\n")
    print("=" * 70)
    print("FIRST INVOCATION")
    print("=" * 70)

    first_result = await graph.ainvoke(
        initial_state,
        config=config,
    )

    print("\nFIRST INVOCATION RESULT")
    print("-" * 70)

    print("Location:", first_result.get("location"))
    print("Cuisine:", first_result.get("cuisine"))
    print("Date:", first_result.get("date"))
    print("Time:", first_result.get("time"))
    print("Party size:", first_result.get("party_size"))

    print("\nAvailable restaurants:")
    for restaurant in first_result.get("available_restaurants", []):
        print(" ", restaurant)

    print("\nAvailability:")
    for availability in first_result.get("availability_results", []):
        print(" ", availability)

    print("\nCurrent step:")
    print(first_result.get("current_step"))

    print("\nLast tool:")
    print(first_result.get("last_tool"))

    print("\nTask status:")
    print(first_result.get("task_status"))

    print("\nLast message:")
    messages = first_result.get("messages", [])

    if messages:
        print(messages[-1].content)

    # =========================================================
    # SECOND INVOCATION
    # USER REQUESTS BOOKING
    # =========================================================

    print()
    print("=" * 70)
    print("SECOND INVOCATION — BOOKING REQUEST")
    print("=" * 70)

    second_result = await graph.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "Yes, book Bella Italia Mayfair at 7pm."
                    )
                )
            ]
        },
        config=config,
    )

    print()
    print("BOOKING REQUEST RESULT")
    print("-" * 70)

    print("Booking requested:")
    print(second_result.get("booking_requested"))

    print("Selected restaurant:")
    print(second_result.get("selected_restaurant_id"))

    print("Task status:")
    print(second_result.get("task_status"))

    print("Interrupts:")
    print(second_result.get("__interrupt__"))

    # =========================================================
    # VERIFY BOOKING APPROVAL INTERRUPT
    # =========================================================

    interrupts = second_result.get("__interrupt__")

    if not interrupts:
        print()
        print("ERROR: Graph did not pause for booking approval.")
        print("The graph should have reached booking_approval().")
        return

    interrupt_value = interrupts[0].value

    print()
    print("=" * 70)
    print("BOOKING APPROVAL REQUIRED")
    print("=" * 70)

    print("Type:")
    print(interrupt_value.get("type"))

    print("Restaurant:")
    print(interrupt_value.get("restaurant"))

    print("Restaurant ID:")
    print(interrupt_value.get("restaurant_id"))

    print("Date:")
    print(interrupt_value.get("date"))

    print("Time:")
    print(interrupt_value.get("time"))

    print("Party size:")
    print(interrupt_value.get("party_size"))

    print("Message:")
    print(interrupt_value.get("message"))

    # ---------------------------------------------------------
    # Assertions
    # ---------------------------------------------------------

    assert second_result.get("booking_requested") is True

    assert second_result.get(
        "selected_restaurant_id"
    ) == "rest-001"

    assert interrupts

    assert interrupt_value.get(
        "type"
    ) == "booking_confirmation"

    assert interrupt_value.get(
        "restaurant_id"
    ) == "rest-001"

    assert interrupt_value.get(
        "date"
    ) == "2026-09-24"

    assert interrupt_value.get(
        "time"
    ) == "19:00"

    assert interrupt_value.get(
        "party_size"
    ) == 2

    # =========================================================
    # VERIFY NO BOOKING HAS HAPPENED YET
    # =========================================================

    snapshot = graph.get_state(config)

    print()
    print("=" * 70)
    print("STATE BEFORE APPROVAL")
    print("=" * 70)

    print("Reservation ID:")
    print(snapshot.values.get("reservation_id"))

    print("Reservation status:")
    print(snapshot.values.get("reservation_status"))

    print("Task status:")
    print(snapshot.values.get("task_status"))

    assert snapshot.values.get("reservation_id") is None

    assert snapshot.values.get(
        "reservation_status"
    ) is None

    # =========================================================
    # THIRD INVOCATION
    # HUMAN APPROVES BOOKING
    # =========================================================

    print()
    print("=" * 70)
    print("THIRD INVOCATION — HUMAN APPROVES")
    print("=" * 70)

    final_result = await graph.ainvoke(
        Command(resume="yes"),
        config=config,
    )

    # =========================================================
    # FINAL RESULT
    # =========================================================

    print()
    print("=" * 70)
    print("FINAL BOOKING RESULT")
    print("=" * 70)

    print("Reservation ID:")
    print(final_result.get("reservation_id"))

    print("Reservation status:")
    print(final_result.get("reservation_status"))

    print("Task status:")
    print(final_result.get("task_status"))

    print("Selected restaurant:")
    print(final_result.get("selected_restaurant_id"))

    # =========================================================
    # FINAL ASSERTIONS
    # =========================================================

    assert final_result.get("reservation_id") is not None

    assert final_result.get(
        "reservation_status"
    ) == "confirmed"

    # Your graph should return completed after successful booking.
    # If your current implementation uses another status,
    # change this assertion to that status.
    assert final_result.get(
        "task_status"
    ) == "completed"

    print()
    print("=" * 70)
    print("THREAD RESUME TEST COMPLETE")
    print("=" * 70)

    print()
    print("SUCCESS:")
    print("1. Restaurant search completed.")
    print("2. Availability was checked.")
    print("3. User explicitly requested booking.")
    print("4. Graph paused for human approval.")
    print("5. Same thread was resumed.")
    print("6. Reservation was created.")
    print("7. Reservation was confirmed.")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())