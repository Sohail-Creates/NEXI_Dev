"""Phase 8 test-pyramid collection, ordering, and reporting policy."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest


# These are interactive physical-device visualizers, not pytest suites. Keeping
# them out of collection also prevents import-time camera/model initialization.
collect_ignore = ["test_fastest_emotion.py", "test_object_detection.py"]

LAYERS = ("unit", "contract", "integration", "resilience", "e2e")
_LAYER_ORDER = {name: index for index, name in enumerate(LAYERS)}
_NODE_LAYERS: dict[str, str] = {}
_RESULTS: Counter[tuple[str, str]] = Counter()


_FILE_DEFAULTS = {
    "test_phase4.py": "unit",
    "test_phase5.py": "integration",
    "test_phase6.py": "integration",
    "test_phase7_cloud_sync.py": "resilience",
    "test_route_naming_normalization.py": "contract",
}

_TEST_OVERRIDES = {
    # Phase 4 producer/consumer and multi-component checks.
    "test_a_reembedding_migration_is_idempotent": "integration",
    "test_a_real_http_learn_then_search": "contract",
    "test_e_llm_contract_clamps_and_provider_failure_is_failure": "contract",
    "test_e_client_response_shape_and_failure_propagation": "contract",
    "test_e_preserves_phase3_llm_focus_deferral": "integration",
    "test_d_audio_uses_central_policy_and_preserves_focus_check": "contract",
    # Phase 5 boundaries and persistence/load checks.
    "test_j_match_issues_token_no_match_does_not_and_expiry_fails": "unit",
    "test_j_new_central_route_wraps_existing_audio_client": "contract",
    "test_g_pickle_migration_twice_and_existing_verification_flow": "integration",
    "test_h_rate_limiter_sustains_burst_without_500": "resilience",
    # Phase 6 direct state machine and inter-service contracts.
    "test_identity_contract_uses_user_id_end_to_end": "contract",
    "test_phase2_resource_authority_regression": "resilience",
    "test_phase2_persistence_regression": "resilience",
    "test_phase2_protected_llm_contract": "contract",
    # Phase 7 direct/static, contract, integration, and resilience checks.
    "test_a_provider_agnostic_client_deduplicates_and_swaps_config": "contract",
    "test_c_outbox_migration_twice_and_conversation_round_trip": "integration",
    "test_d_static_boundary_negative_control_then_clean": "unit",
    "test_g_status_endpoint_is_accurate_and_internally_authenticated": "integration",
}


def _declared_layer(item: pytest.Item) -> str | None:
    explicit = [name for name in LAYERS if item.get_closest_marker(name)]
    if len(explicit) > 1:
        raise pytest.UsageError(f"{item.nodeid} has multiple pyramid layers: {explicit}")
    if explicit:
        return explicit[0]
    name = item.nodeid.rsplit("::", 1)[-1].split("[")[0]
    return _TEST_OVERRIDES.get(name, _FILE_DEFAULTS.get(Path(str(item.path)).name))


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark legacy phase tests centrally and run the pyramid fastest-first."""
    for item in items:
        layer = _declared_layer(item)
        if layer:
            item.add_marker(getattr(pytest.mark, layer))
            _NODE_LAYERS[item.nodeid] = layer
    items.sort(key=lambda item: (_LAYER_ORDER.get(_NODE_LAYERS.get(item.nodeid, ""), 99), item.nodeid))


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.when == "call":
        layer = _NODE_LAYERS.get(report.nodeid, "unclassified")
        _RESULTS[(layer, report.outcome)] += 1


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    terminalreporter.write_sep("=", "PHASE 8 PYRAMID SUMMARY")
    for layer in LAYERS:
        passed = _RESULTS[(layer, "passed")]
        failed = _RESULTS[(layer, "failed")]
        skipped = _RESULTS[(layer, "skipped")]
        selected = passed + failed + skipped
        terminalreporter.write_line(
            f"{layer.upper():10} selected={selected} passed={passed} failed={failed} skipped={skipped}"
        )
