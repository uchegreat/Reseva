import anyio

from agent.mcp_client import search_restaurants


async def main():

    restaurants = await search_restaurants(
        location="Mayfair",
        cuisine="Italian",
    )

    print("\nRestaurants found:")

    for restaurant in restaurants:
        print(restaurant)


if __name__ == "__main__":
    anyio.run(main)