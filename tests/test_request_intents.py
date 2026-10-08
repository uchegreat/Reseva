from agent.extractor import extract_reservation_update


def test_extract_create_intent():
    state = {
        "available_restaurants": [],
        "availability_results": [],
    }

    result = extract_reservation_update(
        "Book me a table for 2 people tomorrow at 7pm.",
        state,
    )

    assert result.booking_requested is True
    assert result.modification_requested in (None, False)
    assert result.cancellation_requested in (None, False)


def test_extract_modify_intent():
    state = {
        "available_restaurants": [],
        "availability_results": [],
    }

    result = extract_reservation_update(
        "Change my reservation to 8pm.",
        state,
    )

    assert result.modification_requested is True
    assert result.booking_requested in (None, False)
    assert result.cancellation_requested in (None, False)
    assert result.modification_time == "20:00"


def test_extract_cancel_intent():
    state = {
        "available_restaurants": [],
        "availability_results": [],
    }

    result = extract_reservation_update(
        "Cancel my reservation res-10001.",
        state,
    )

    assert result.cancellation_requested is True
    assert result.booking_requested in (None, False)
    assert result.modification_requested in (None, False)
    assert result.reservation_id_to_modify == "res-10001"