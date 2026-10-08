from agent.extractor import extract_reservation_update


result = extract_reservation_update(
    "Yes, book Bella Italia Mayfair.",
    {
        "location": "Mayfair",
        "cuisine": "Italian",
        "date": "2026-09-18",
        "time": "19:00",
        "party_size": 2,
        "budget": None,
        "selected_restaurant_id": None,
    },
)

print(result)