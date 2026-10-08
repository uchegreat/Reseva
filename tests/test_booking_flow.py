
import asyncio
import uuid

import pytest
from database.db import SessionLocal
from database.models import Reservation, ReservationEvent
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from tests.postgres_graph import PostgresGraphContext


if __name__ != "__main__":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )


@pytest.mark.anyio
async def test_complete_booking_flow():

    thread_id = f"test-booking-flow-{uuid.uuid4()}"

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    # -------------------------------------------------
    # POSTGRES GRAPH CONTEXT
    # -------------------------------------------------

    async with PostgresGraphContext() as graph:

        # -------------------------------------------------
        # STEP 1
        # User searches for a restaurant
        # -------------------------------------------------

        state = {
            "messages": [
                HumanMessage(
                    content="Find me an Italian restaurant in Mayfair."
                )
            ],

            "user_id": "test-user",
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

            "task_status": "started",
        }

        result = await graph.ainvoke(
            state,
            config=config,
        )

        print("\n" + "=" * 60)
        print("--- STEP 1: RESTAURANT SEARCH ---")
        print("=" * 60)

        print(
            "Selected restaurant:",
            result.get("selected_restaurant_id")
        )

        print(
            "Available restaurants:",
            result.get("available_restaurants")
        )

        print(
            "Task status:",
            result.get("task_status")
        )

        print(
            "Location:",
            result.get("location")
        )

        print(
            "Cuisine:",
            result.get("cuisine")
        )

        print("\nMessages:")

        for message in result.get("messages", []):
            print(
                "  -",
                type(message).__name__,
                "| name=",
                getattr(message, "name", None),
                "| content=",
                getattr(message, "content", None),
            )

        # -------------------------------------------------
        # STEP 2
        # User provides date, time and party size
        # -------------------------------------------------

        result = await graph.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content="Tomorrow at 7pm for 2 people."
                    )
                ]
            },
            config=config,
        )

        print("\n" + "=" * 60)
        print("--- STEP 2: DATE / TIME / PARTY SIZE ---")
        print("=" * 60)

        print(
            "Selected restaurant:",
            result.get("selected_restaurant_id")
        )

        print(
            "Date:",
            result.get("date")
        )

        print(
            "Time:",
            result.get("time")
        )

        print(
            "Party size:",
            result.get("party_size")
        )

        print(
            "Availability results:",
            result.get("availability_results")
        )

        print(
            "Task status:",
            result.get("task_status")
        )

        # -------------------------------------------------
        # STEP 3
        # User asks Reseva to book it
        # -------------------------------------------------

        result = await graph.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content="Book it."
                    )
                ]
            },
            config=config,
        )

        print("\n" + "=" * 60)
        print("--- STEP 3: BOOKING REQUEST ---")
        print("=" * 60)

        print(
            "Booking requested:",
            result.get("booking_requested")
        )

        print(
            "Selected restaurant:",
            result.get("selected_restaurant_id")
        )

        print(
            "Date:",
            result.get("date")
        )

        print(
            "Time:",
            result.get("time")
        )

        print(
            "Party size:",
            result.get("party_size")
        )

        print(
            "Task status:",
            result.get("task_status")
        )

        # -------------------------------------------------
        # STEP 4
        # Reseva should pause for human approval
        # -------------------------------------------------

        snapshot = await graph.aget_state(config)

        print("\n" + "=" * 60)
        print("--- STEP 4: APPROVAL ---")
        print("=" * 60)

        print(
            "Current task status:",
            snapshot.values.get("task_status")
        )

        print(
            "Selected restaurant:",
            snapshot.values.get(
                "selected_restaurant_id"
            )
        )

        print(
            "Date:",
            snapshot.values.get("date")
        )

        print(
            "Time:",
            snapshot.values.get("time")
        )

        print(
            "Party size:",
            snapshot.values.get("party_size")
        )

        print(
            "Booking requested:",
            snapshot.values.get("booking_requested")
        )

        print(
            "Availability results:",
            snapshot.values.get("availability_results")
        )

        print(
            "Interrupts:",
            snapshot.interrupts
        )

        # The graph should be paused here.
        assert snapshot.interrupts

        # -------------------------------------------------
        # STEP 5
        # User approves the reservation
        # -------------------------------------------------

        result = await graph.ainvoke(
            Command(
                resume="yes"
            ),
            config=config,
        )

        print("\n" + "=" * 60)
        print("--- STEP 5: BOOKING APPROVED ---")
        print("=" * 60)

        print(
            "Reservation ID:",
            result.get("reservation_id")
        )

        print(
            "Reservation status:",
            result.get("reservation_status")
        )

        print(
            "Task status:",
            result.get("task_status")
        )

        # -------------------------------------------------
        # STEP 6
        # Check final state
        # -------------------------------------------------

        final_state = await graph.aget_state(config)

        print("\n" + "=" * 60)
        print("--- STEP 6: FINAL STATE ---")
        print("=" * 60)

        print(
            "Reservation ID:",
            final_state.values.get(
                "reservation_id"
            )
        )

        print(
            "Reservation status:",
            final_state.values.get(
                "reservation_status"
            )
        )

        print(
            "Task status:",
            final_state.values.get(
                "task_status"
            )
        )

        print(
            "Selected restaurant:",
            final_state.values.get(
                "selected_restaurant_id"
            )
        )

    # -------------------------------------------------
    # DATABASE CLEANUP
    # -------------------------------------------------

    db = SessionLocal()

    try:
        reservation = (
            db.query(Reservation)
            .filter(
                Reservation.reservation_id == "res-10001"
            )
            .first()
        )

        if reservation:
            db.query(ReservationEvent).filter(
                ReservationEvent.reservation_id == reservation.id
            ).delete(
                synchronize_session=False
            )

            db.delete(reservation)
            db.commit()

    finally:
        db.close()


