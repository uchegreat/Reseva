from database.db import SessionLocal
from database.models import Restaurant


RESTAURANTS = [
    {
        "id": "rest-001",
        "name": "Bella Italia Mayfair",
        "location": "Mayfair",
        "cuisine": "Italian",
    },
    {
        "id": "rest-002",
        "name": "La Tavola",
        "location": "Mayfair",
        "cuisine": "Italian",
    },
    {
        "id": "rest-003",
        "name": "The Mayfair Grill",
        "location": "Mayfair",
        "cuisine": "British",
    },
    {
        "id": "rest-004",
        "name": "Sushi House Mayfair",
        "location": "Mayfair",
        "cuisine": "Japanese",
    },
]


def seed_restaurants():
    db = SessionLocal()

    try:
        for restaurant_data in RESTAURANTS:
            existing = (
                db.query(Restaurant)
                .filter(
                    Restaurant.id == restaurant_data["id"]
                )
                .first()
            )

            if existing:
                continue

            restaurant = Restaurant(**restaurant_data)
            db.add(restaurant)

        db.commit()

        print("Restaurants seeded successfully.")

    finally:
        db.close()


if __name__ == "__main__":
    seed_restaurants()