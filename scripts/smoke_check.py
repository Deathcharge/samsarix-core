# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Verify the installed wheel's public canonical and compatibility exports."""

from __future__ import annotations

import helix_core
import samsarix_core


def _require(condition: bool, message: str) -> None:
    """Fail the smoke check even when Python assertions are optimized away."""

    if not condition:
        raise RuntimeError(message)


def main() -> None:
    """Assert the release-critical import and model surface."""

    canonical_exports = (
        samsarix_core.MCPServer,
        samsarix_core.ToolPolicyContext,
        samsarix_core.ToolPolicyDecision,
        samsarix_core.ToolRuntime,
        samsarix_core.serve_stdio,
    )
    legacy_exports = (
        helix_core.MCPServer,
        helix_core.ToolPolicyContext,
        helix_core.ToolPolicyDecision,
        helix_core.ToolRuntime,
        helix_core.serve_stdio,
    )
    _require(legacy_exports == canonical_exports, "legacy callable exports differ")
    _require(
        helix_core.ToolRateLimit is samsarix_core.ToolRateLimit,
        "legacy rate-limit export differs",
    )
    _require(
        helix_core.ToolCircuitBreaker is samsarix_core.ToolCircuitBreaker,
        "legacy circuit-policy export differs",
    )
    _require(
        helix_core.ToolCircuitState is samsarix_core.ToolCircuitState,
        "legacy circuit-state export differs",
    )
    _require(
        helix_core.__version__ == samsarix_core.__version__,
        "legacy package version differs",
    )
    _require(
        samsarix_core.ToolRateLimit(calls=1, period_seconds=1).burst_capacity == 1,
        "rate-limit model behavior differs",
    )
    circuit = samsarix_core.ToolCircuitBreaker(
        failure_threshold=1,
        recovery_timeout_seconds=1,
    )
    _require(circuit.recovery_timeout_seconds == 1.0, "circuit model behavior differs")
    _require(
        samsarix_core.ToolCircuitState.CLOSED.value == "closed",
        "circuit state value differs",
    )
    print(samsarix_core.__version__)


if __name__ == "__main__":
    main()
