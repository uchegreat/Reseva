import anyio

from agent.mcp_client import check_availability


async def main():

    result = await check_availability.ainvoke(
        {
            "restaurant_id": "rest-001",
            "date": "2026-09-17",
            "time": "19:00",
            "party_size": 2,
        }
    )

    print("\nAvailability result:")
    print(result)


if __name__ == "__main__":
    anyio.run(main)