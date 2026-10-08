import asyncio
import uuid

import pytest
from langchain_core.messages import HumanMessage
from tests.postgres_graph import PostgresGraphContext


if __name__ != "__main__":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )


@pytest.mark.anyio
async def test_alternative_time_is_rechecked():

    thread_id = f"test-recovery-flow-{uuid.uuid4()}"

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    async with PostgresGraphContext() as graph:

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

        # ---------------------------------------------------------
        # STEP 1
        # Search for restaurants
        # ---------------------------------------------------------

        await graph.ainvoke(
            state,
            config=config,
        )

        # ---------------------------------------------------------
        # STEP 2
        # Give date, unavailable time and party size
        # ---------------------------------------------------------

        await graph.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content="Tomorrow at 9pm for 2 people."
                    )
                ]
            },
            config=config,
        )

        # ---------------------------------------------------------
        # STEP 3
        # Select Bella Italia
        # ---------------------------------------------------------

        await graph.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content="Let's go with Bella Italia Mayfair."
                    )
                ]
            },
            config=config,
        )

        state_after_selection = await graph.aget_state(
            config
        )

        print("\n--- STEP 3 ---")
        print(
            "Selected restaurant:",
            state_after_selection.values.get(
                "selected_restaurant_id"
            )
        )

        print(
            "Task status:",
            state_after_selection.values.get(
                "task_status"
            )
        )

        # Bella Italia should be selected.
        assert (
            state_after_selection.values.get(
                "selected_restaurant_id"
            )
            == "rest-001"
        )

        # Recovery should have found alternatives.
        assert (
            state_after_selection.values.get(
                "task_status"
            )
            == "alternatives_found"
        )

        # ---------------------------------------------------------
        # STEP 4
        # User chooses 7pm
        # ---------------------------------------------------------

        await graph.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content="I'll take 7pm."
                    )
                ]
            },
            config=config,
        )

        state_after_time_selection = await graph.aget_state(
            config
        )

        print("\n--- STEP 4 ---")
        print(
            "Selected time:",
            state_after_time_selection.values.get(
                "time"
            )
        )

        print(
            "Availability results:",
            state_after_time_selection.values.get(
                "availability_results"
            )
        )

        print(
            "Task status:",
            state_after_time_selection.values.get(
                "task_status"
            )
        )

        # 7pm should be converted to 19:00.
        assert (
            state_after_time_selection.values.get(
                "time"
            )
            == "19:00"
        )

        # ---------------------------------------------------------
        # STEP 5
        # Verify 19:00 was checked
        # ---------------------------------------------------------

        availability_results = (
            state_after_time_selection.values.get(
                "availability_results",
                []
            )
        )

        bella_results = [
            result
            for result in availability_results
            if result.get("restaurant_id") == "rest-001"
        ]

        latest_bella_result = bella_results[-1]

        print(
            "Latest Bella availability:",
            latest_bella_result
        )

        # Bella Italia should be available at 19:00.
        assert (
            latest_bella_result.get("available")
            is True
        )

        assert (
            latest_bella_result.get("time")
            == "19:00"
        )