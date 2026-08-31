# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Bounded regression cases for derived diagnostics and numeric normalization."""

from __future__ import annotations

import json
from typing import Annotated, TypedDict

import pytest

from samsarix_core import (
    ToolCall,
    ToolDefinitionError,
    ToolPolicyContext,
    ToolPolicyDecision,
    ToolRuntime,
    ToolStatus,
    samsarix_tool,
)
from samsarix_core.errors import ToolArgumentError
from samsarix_core.schema import validate_value


class Row(TypedDict):
    value: int


class NestedRows(TypedDict):
    first: Row
    second: Row


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["k", "\U0001f680", "\n"])
async def test_diagnostics_bound_long_paths_and_many_fields(prefix: str) -> None:
    executed = False
    authorized = False

    @samsarix_tool
    def inspect_rows(payload: dict[str, Row]) -> int:
        """Count well-formed rows."""
        nonlocal executed
        executed = True
        return len(payload)

    async def policy(context: ToolPolicyContext) -> ToolPolicyDecision:
        nonlocal authorized
        authorized = True
        return ToolPolicyDecision.ALLOW

    # At most ~1 MiB of diagnostics on the old implementation, not the full-scale
    # resource-exhaustion payload. The original input remains well below its cap.
    arguments = {"payload": {prefix * 4096: {f"x{i}": 0 for i in range(128)}}}
    assert len(json.dumps(arguments).encode()) < 100_000
    async with ToolRuntime(policy=policy) as runtime:
        runtime.register(inspect_rows)
        result = await runtime.invoke("inspect_rows", arguments)
        assert result.status is ToolStatus.INVALID_ARGUMENTS
        assert not executed and not authorized
        assert result.error is not None and result.error.details is not None
        issues = result.error.details["issues"]
        assert len(issues) <= 64
        assert issues[-1]["code"] == "issues_truncated"
        assert all(len(item["path"]) <= 128 and len(item["message"]) <= 128 for item in issues)
        assert len(json.dumps(result.to_dict(), ensure_ascii=True).encode()) < 110_000
        assert runtime.metrics().pending_invocations == 0


@pytest.mark.asyncio
async def test_top_level_diagnostics_and_nested_aggregation_are_bounded() -> None:
    @samsarix_tool
    def empty() -> None:
        """Accept no arguments."""

    async with ToolRuntime() as runtime:
        runtime.register(empty)
        result = await runtime.invoke("empty", {f"{i}-" + "z" * 4096: 0 for i in range(80)})
    assert result.error is not None and result.error.details is not None
    issues = result.error.details["issues"]
    assert len(issues) == 64
    assert all(len(item["path"]) <= 128 and len(item["message"]) <= 128 for item in issues)
    assert issues[-1]["code"] == "issues_truncated"

    invalid = {"first": {f"x{i}": 0 for i in range(40)}, "second": {f"y{i}": 0 for i in range(40)}}
    with pytest.raises(ToolArgumentError) as caught:
        validate_value(invalid, NestedRows, path="$")
    assert len(caught.value.issues) == 64
    assert caught.value.issues[-1].code == "issues_truncated"


def test_bounded_failed_union_branch_still_tries_valid_alternative() -> None:
    value = {f"x{i}": 0 for i in range(100)}
    assert validate_value(value, Row | dict[str, int], path="$") == value


def test_short_diagnostics_and_valid_long_keys_are_unchanged() -> None:
    with pytest.raises(ToolArgumentError) as caught:
        validate_value({"value": "wrong"}, Row, path="$.payload")
    assert [issue.to_dict() for issue in caught.value.issues] == [
        {"path": "$.payload.value", "code": "type_mismatch", "message": "Expected integer"}
    ]
    value = {"k" * 4096: {"value": 1}}
    assert validate_value(value, dict[str, Row], path="$") == value


def test_issue_collection_stops_at_cap() -> None:
    visited = 0

    class CountedFields(dict):
        def __iter__(self):
            nonlocal visited
            for key in super().__iter__():
                visited += 1
                yield key

    with pytest.raises(ToolArgumentError) as caught:
        validate_value(CountedFields({f"x{i}": 0 for i in range(100)}), Row, path="$")
    assert visited == 64
    assert len(caught.value.issues) == 64
    assert caught.value.issues[-1].code == "issues_truncated"


@pytest.mark.parametrize(
    ("annotation", "value"),
    [
        (float, 10**1000),
        (Annotated[float, "number"], -(10**1000)),
        (list[float], [10**1000]),
        (tuple[float, ...], [10**1000]),
        (dict[str, float], {"x": 10**1000}),
    ],
    ids=["scalar", "annotated-negative", "list", "tuple", "dictionary"],
)
def test_overflowing_numbers_are_validation_errors(annotation, value) -> None:
    with pytest.raises(ToolArgumentError) as caught:
        validate_value(value, annotation, path="$")
    assert caught.value.issues[0].code == "type_mismatch"
    assert caught.value.issues[0].message == "Expected finite number"


def test_float_first_union_preserves_large_integer_alternative() -> None:
    value = 10**1000
    assert validate_value(value, float | int, path="$") == value
    assert validate_value(value, int | float, path="$") == value


@pytest.mark.asyncio
@pytest.mark.parametrize("pending_capacity", [1, 256])
async def test_bad_numeric_argument_does_not_abort_other_batch_items(pending_capacity: int) -> None:
    seen: list[float] = []

    @samsarix_tool
    async def number(value: float) -> float:
        """Record accepted finite numbers."""
        seen.append(value)
        return value

    async with ToolRuntime(max_pending_invocations=pending_capacity) as runtime:
        runtime.register(number)
        results = await runtime.invoke_many(
            [ToolCall("number", {"value": 10**1000}), ToolCall("number", {"value": 7})]
        )
        assert [result.status for result in results] == [
            ToolStatus.INVALID_ARGUMENTS,
            ToolStatus.SUCCESS,
        ]
        assert results[1].output == 7.0
        assert seen == [7.0]
        assert runtime.metrics().pending_invocations == 0
        assert (await runtime.invoke("number", {"value": 8})).success


def test_overflowing_float_default_is_a_definition_error() -> None:
    with pytest.raises(ToolDefinitionError, match="Default"):

        @samsarix_tool
        def number(value: float = 10**1000) -> float:
            """Reject an unrepresentable default during definition."""
            return value


@pytest.mark.asyncio
async def test_overflowing_float_output_is_a_contract_error() -> None:
    @samsarix_tool
    def number() -> float:
        """Return an integer outside the declared float range."""
        return 10**1000

    async with ToolRuntime() as runtime:
        runtime.register(number)
        result = await runtime.invoke("number", {})
    assert result.status is ToolStatus.FAILED
    assert result.error is not None and result.error.code == "invalid_output"
