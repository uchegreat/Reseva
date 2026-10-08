import anyio

from agent.mcp_client import create_reservation


async def main():

    result = await create_reservation.ainvoke({
        "restaurant_id": "rest-001",
        "date": "2026-09-18",
        "time": "19:00",
        "party_size": 2,
    })

    print("Reservation result:")
    print(result)


if __name__ == "__main__":
    anyio.run(main)