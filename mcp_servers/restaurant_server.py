from mcp.server import MCPServer

from database.db import SessionLocal
from database.repository import (
    save_reservation,
    get_reservation as get_reservation_from_db,
    modify_reservation as modify_reservation_from_db,
    cancel_reservation as cancel_reservation_from_db,
)


mcp = MCPServer("Reseva Restaurant Server")


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


@mcp.tool()
def search_restaurants(
    location: str,
    cuisine: str | None = None,
) -> list[dict]:
    """
    Search for restaurants by location and optionally cuisine.
    """

    results = []

    for restaurant in RESTAURANTS:
        if restaurant["location"].lower() != location.lower():
            continue

        if cuisine and restaurant["cuisine"].lower() != cuisine.lower():
            continue

        results.append(restaurant)

    return results


@mcp.tool()
def check_availability(
    restaurant_id: str,
    date: str,
    time: str,
    party_size: int,
) -> dict:
    """
    Check whether a restaurant has availability for a requested
    date, time and party size.
    """

    available_slots = {
        "rest-001": ["18:00", "18:30", "19:00", "19:30", "20:00"],
        "rest-002": ["18:00", "18:30", "20:00", "20:30"],
    }

    if restaurant_id not in available_slots:
        return {
            "available": False,
            "restaurant_id": restaurant_id,
            "date": date,
            "time": time,
            "party_size": party_size,
            "reason": "Restaurant is not currently available through Reseva.",
        }

    if time in available_slots[restaurant_id]:
        return {
            "available": True,
            "restaurant_id": restaurant_id,
            "date": date,
            "time": time,
            "party_size": party_size,
            "message": "A table is available.",
        }

    return {
        "available": False,
        "restaurant_id": restaurant_id,
        "date": date,
        "time": time,
        "party_size": party_size,
        "message": "No table is available at the requested time.",
        "alternative_times": available_slots[restaurant_id],
    }


@mcp.tool()
def get_alternative_times(
    restaurant_id: str,
    date: str,
    requested_time: str,
    party_size: int,
) -> dict:
    """
    Find alternative available times for a restaurant
    when the requested time is unavailable.
    """

    available_slots = {
        "rest-001": ["18:00", "18:30", "19:00", "19:30", "20:00"],
        "rest-002": ["18:00", "18:30", "20:00", "20:30"],
    }

    if restaurant_id not in available_slots:
        return {
            "success": False,
            "restaurant_id": restaurant_id,
            "date": date,
            "requested_time": requested_time,
            "party_size": party_size,
            "alternative_times": [],
            "message": "No alternative times are available.",
        }

    alternatives = [
        time
        for time in available_slots[restaurant_id]
        if time != requested_time
    ]

    return {
        "success": True,
        "restaurant_id": restaurant_id,
        "date": date,
        "requested_time": requested_time,
        "party_size": party_size,
        "alternative_times": alternatives,
        "message": "Alternative times found.",
    }


@mcp.tool()
def create_reservation(
    restaurant_id: str,
    date: str,
    time: str,
    party_size: int,
) -> dict:
    """
    Create and persist a restaurant reservation through Reseva.
    """

    restaurant = next(
        (
            item
            for item in RESTAURANTS
            if item["id"] == restaurant_id
        ),
        None,
    )

    if not restaurant:
        return {
            "success": False,
            "message": "Restaurant not found.",
        }

    # ---------------------------------------------------------
    # Validate availability before creating the reservation
    # ---------------------------------------------------------

    available_slots = {
        "rest-001": ["18:00", "18:30", "19:00", "19:30", "20:00"],
        "rest-002": ["18:00", "18:30", "20:00", "20:30"],
    }

    if restaurant_id not in available_slots:
        return {
            "success": False,
            "restaurant_id": restaurant_id,
            "message": "Restaurant is not currently available through Reseva.",
        }

    if time not in available_slots[restaurant_id]:
        return {
            "success": False,
            "restaurant_id": restaurant_id,
            "date": date,
            "time": time,
            "party_size": party_size,
            "message": "The requested time is not available.",
        }

    # ---------------------------------------------------------
    # Generate a unique Reseva reservation ID
    # ---------------------------------------------------------

    import uuid

    reservation_id = f"res-{uuid.uuid4().hex[:8]}"

    # ---------------------------------------------------------
    # Persist reservation
    # ---------------------------------------------------------

    db = SessionLocal()

    try:
        reservation = save_reservation(
            db,
            {
                "reservation_id": reservation_id,
                "restaurant_id": restaurant_id,
                "date": date,
                "time": time,
                "party_size": party_size,
            },
        )

        return {
    "success": True,
    "reservation_id": reservation.reservation_id,
    "restaurant_id": reservation.restaurant_id,
    "restaurant_name": restaurant["name"],
    "date": reservation.date,
    "time": reservation.time,
    "party_size": reservation.party_size,
    "status": reservation.status,
    "message": "Reservation successfully created and persisted through Reseva.",
}

    finally:
        db.close()

@mcp.tool()
def get_reservation(reservation_id: str) -> dict:
    """
    Retrieve an existing reservation from the Reseva PostgreSQL database.
    """

    db = SessionLocal()

    try:
        reservation = get_reservation_from_db(
            db,
            reservation_id,
        )

        if not reservation:
            return {
                "success": False,
                "reservation_id": reservation_id,
                "message": "Reservation not found.",
            }

        restaurant = next(
            (
                item
                for item in RESTAURANTS
                if item["id"] == reservation.restaurant_id
            ),
            None,
        )

        return {
            "success": True,
            "reservation": {
                "reservation_id": reservation.reservation_id,
                "restaurant_id": reservation.restaurant_id,
                "restaurant_name": (
                    restaurant["name"]
                    if restaurant
                    else "Unknown restaurant"
                ),
                "date": reservation.date,
                "time": reservation.time,
                "party_size": reservation.party_size,
                "status": reservation.status,
            },
        }

    finally:
        db.close()

@mcp.tool()
def modify_reservation(
    reservation_id: str,
    date: str | None = None,
    time: str | None = None,
    party_size: int | None = None,
) -> dict:
    """
    Modify an existing reservation in the Reseva database.
    """

    db = SessionLocal()

    try:
        reservation = modify_reservation_from_db(
            db,
            reservation_id,
            date=date,
            time=time,
            party_size=party_size,
        )

        if not reservation:
            return {
                "success": False,
                "reservation_id": reservation_id,
                "message": "Reservation not found.",
            }

        restaurant = next(
            (
                item
                for item in RESTAURANTS
                if item["id"] == reservation.restaurant_id
            ),
            None,
        )

        return {
            "success": True,
            "reservation": {
                "reservation_id": reservation.reservation_id,
                "restaurant_id": reservation.restaurant_id,
                "restaurant_name": (
                    restaurant["name"]
                    if restaurant
                    else "Unknown restaurant"
                ),
                "date": reservation.date,
                "time": reservation.time,
                "party_size": reservation.party_size,
                "status": reservation.status,
            },
            "message": "Reservation successfully modified through Reseva.",
        }

    finally:
        db.close()

@mcp.tool()
def cancel_reservation(reservation_id: str) -> dict:
    """Cancel an existing reservation in the Reseva database."""

    db = SessionLocal()

    try:
        reservation = cancel_reservation_from_db(
            db,
            reservation_id,
        )

        if not reservation:
            return {
                "success": False,
                "reservation_id": reservation_id,
                "message": "Reservation not found.",
            }

        restaurant = next(
            (
                item
                for item in RESTAURANTS
                if item["id"] == reservation.restaurant_id
            ),
            None,
        )

        return {
            "success": True,
            "reservation": {
                "reservation_id": reservation.reservation_id,
                "restaurant_id": reservation.restaurant_id,
                "restaurant_name": (
                    restaurant["name"]
                    if restaurant
                    else "Unknown restaurant"
                ),
                "date": reservation.date,
                "time": reservation.time,
                "party_size": reservation.party_size,
                "status": reservation.status,
            },
            "message": "Reservation successfully cancelled through Reseva.",
        }

    finally:
        db.close()

if __name__ == "__main__":
    mcp.run(transport="stdio")