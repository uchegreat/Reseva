from agent.extractor import extract_reservation_update


def test_book_it_selects_only_available_restaurant():

    state = {
        "location": "Mayfair",
        "cuisine": "Italian",
        "date": "2026-09-18",
        "time": "19:00",
        "party_size": 2,
        "budget": None,

        "selected_restaurant_id": None,

        "available_restaurants": [
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
        ],

        "availability_results": [
            {
                "available": True,
                "restaurant_id": "rest-001",
                "date": "2026-09-18",
                "time": "19:00",
                "party_size": 2,
            },
            {
                "available": False,
                "restaurant_id": "rest-002",
                "date": "2026-09-18",
                "time": "19:00",
                "party_size": 2,
            },
        ],
    }

    result = extract_reservation_update(
        "Book it.",
        state,
    )

    print("\nExtractor result:")
    print(result)

    assert result.booking_requested is True
    assert result.selected_restaurant_id == "rest-001"