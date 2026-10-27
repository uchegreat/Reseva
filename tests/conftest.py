"""Shared pytest configuration.

Some tests call the real Claude API, or build on something that does. They need
a real ANTHROPIC_API_KEY, so they cannot run on CI, where only placeholder keys
exist. Set RESEVA_SKIP_LIVE_TESTS=1 to skip them (CI does this). Leave it unset
to run the whole suite locally.
"""

import os

import pytest

SKIP_LIVE_TESTS = os.getenv("RESEVA_SKIP_LIVE_TESTS") == "1"

# These files create a real Claude client when they are imported, so they fail
# during collection without a real key.
LIVE_TEST_FILES = [
    "test_claude_tools.py",
    "test_selection.py",
]

# Tests that need the real Claude API at run time.
LIVE_TESTS = {
    "tests/test_adaptive_execution.py::test_evaluator_detects_failed_execution",
    "tests/test_adaptive_execution.py::test_adaptive_planner_changes_the_plan",
    "tests/test_adaptive_execution.py::test_original_request_is_preserved_after_adaptation",
    "tests/test_advanced_graph.py::test_advanced_graph_loads_memory",
    "tests/test_advanced_memory_learning.py::test_advanced_graph_learns_user_preference",
    "tests/test_advanced_planning.py::test_advanced_graph_creates_plan",
    "tests/test_advanced_postgres.py::test_advanced_graph_with_postgres_checkpointer",
    "tests/test_api_chat_runtime.py::test_api_runtime_booking_interrupt",
    "tests/test_booking_flow.py::test_complete_booking_flow",
    "tests/test_extractor.py::test_book_it_selects_only_available_restaurant",
    "tests/test_human_approval.py::test_human_approval_pauses_and_resumes",
    "tests/test_human_approval.py::test_human_approval_rejection_does_not_create_reservation",
    "tests/test_memory_extractor.py::test_extract_preferred_cuisine",
    "tests/test_memory_extractor.py::test_extract_preferred_location",
    "tests/test_memory_extractor.py::test_extract_typical_party_size",
    "tests/test_memory_extractor.py::test_extract_budget_preference",
    "tests/test_memory_extractor.py::test_do_not_store_temporary_booking_details",
    "tests/test_postgres_checkpointer.py::test_postgres_checkpointer",
    "tests/test_recovery_flow.py::test_alternative_time_is_rechecked",
    "tests/test_request_intents.py::test_extract_create_intent",
    "tests/test_request_intents.py::test_extract_modify_intent",
    "tests/test_request_intents.py::test_extract_cancel_intent",
    "tests/test_thread_persistence.py::test_thread_persists_across_reconnect",
    "tests/test_thread_resume.py::test_booking_resumes_after_reconnect",
    "tests/test_tool_failure_recovery.py::test_mcp_failure_requires_adaptation",
    "tests/test_tool_failure_recovery.py::test_retry_exhaustion_produces_adaptable_execution_state",
}

collect_ignore = LIVE_TEST_FILES if SKIP_LIVE_TESTS else []


def pytest_collection_modifyitems(config, items):
    if not SKIP_LIVE_TESTS:
        return

    skip = pytest.mark.skip(reason="needs a real Anthropic API key")

    for item in items:
        # Parametrised tests look like "name[asyncio]"; match on the base name.
        if item.nodeid.split("[")[0] in LIVE_TESTS:
            item.add_marker(skip)