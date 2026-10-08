from agent.memory_extractor import extract_memory


def test_extract_preferred_cuisine():
    result = extract_memory(
        "I really like Italian food."
    )

    assert result.memory_type == "preference"
    assert result.memory_key == "preferred_cuisine"
    assert result.memory_value == "Italian"


def test_extract_preferred_location():
    result = extract_memory(
        "I normally eat around Mayfair."
    )

    assert result.memory_type == "preference"
    assert result.memory_key == "preferred_location"
    assert result.memory_value == "Mayfair"


def test_extract_typical_party_size():
    result = extract_memory(
        "I usually go out with four people."
    )

    assert result.memory_type == "preference"
    assert result.memory_key == "typical_party_size"
    assert result.memory_value == "4"


def test_extract_budget_preference():
    result = extract_memory(
        "I prefer affordable restaurants."
    )

    assert result.memory_type == "preference"
    assert result.memory_key == "budget_preference"
    assert result.memory_value == "affordable"


def test_do_not_store_temporary_booking_details():
    result = extract_memory(
        "Book me an Italian restaurant tomorrow at 7pm."
    )

    assert result.memory_type is None
    assert result.memory_key is None
    assert result.memory_value is None