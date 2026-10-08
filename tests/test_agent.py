import asyncio

from langgraph.types import Command

from tests.postgres_graph import PostgresGraphContext


# Psycopg async connections do not work with the Windows ProactorEventLoop.
asyncio.set_event_loop_policy(
    asyncio.WindowsSelectorEventLoopPolicy()
)


config = {
    "configurable": {
        "thread_id": "reseva-test-001"
    }
}


async def main():

    async with PostgresGraphContext() as graph:

        # -------------------------------------------------
        # STEP 1
        # -------------------------------------------------

        result1 = await graph.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Find me an Italian restaurant in Mayfair."
                        ),
                    }
                ],
                "user_id": "user-001",
                "thread_id": "reseva-test-001",
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
                "task_status": "new",
            },
            config,
        )

        print("\nFIRST CALL:")
        print(result1)

        # -------------------------------------------------
        # STEP 2
        # -------------------------------------------------

        result2 = await graph.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Make it for 7pm tomorrow.",
                    }
                ]
            },
            config,
        )

        print("\nSECOND CALL:")
        print(result2)

        # -------------------------------------------------
        # STEP 3
        # -------------------------------------------------

        result3 = await graph.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Yes, book Bella Italia Mayfair."
                        ),
                    }
                ]
            },
            config,
        )

        print("\nTHIRD CALL:")
        print(result3)

        # -------------------------------------------------
        # STEP 4 - APPROVAL
        # -------------------------------------------------

        snapshot = await graph.aget_state(config)

        print("\nAPPROVAL STATE:")
        print("Task status:", snapshot.values.get("task_status"))
        print(
            "Selected restaurant:",
            snapshot.values.get("selected_restaurant_id"),
        )
        print("Interrupts:", snapshot.interrupts)

        # -------------------------------------------------
        # STEP 5 - RESUME AFTER APPROVAL
        # -------------------------------------------------

        result4 = await graph.ainvoke(
            Command(resume="yes"),
            config,
        )

        print("\nFOURTH CALL - AFTER APPROVAL:")
        print(result4)

        # -------------------------------------------------
        # FINAL STATE
        # -------------------------------------------------

        final_state = await graph.aget_state(config)

        print("\nFINAL STATE:")
        print(
            "Reservation ID:",
            final_state.values.get("reservation_id"),
        )
        print(
            "Reservation status:",
            final_state.values.get("reservation_status"),
        )
        print(
            "Task status:",
            final_state.values.get("task_status"),
        )


if __name__ == "__main__":
    asyncio.run(main())