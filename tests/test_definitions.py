# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import math
import sys
from typing import Annotated, Any, Literal, TypedDict

import pytest

from samsarix_core import (
    DuplicateToolError,
    RegistryCapacityError,
    ToolDefinitionError,
    ToolNotFoundError,
    ToolRegistry,
)
from samsarix_core import (
    samsarix_tool as helix_tool,
)

MARKER = object()


class Coordinates(TypedDict):
    latitude: Annotated[float, "Latitude in decimal degrees"]
    longitude: float


class OptionalSearchFields(TypedDict, total=False):
    label: str
    limit: int


class SearchRequest(OptionalSearchFields):
    query: Annotated[str, "Search phrase"]
    coordinates: Coordinates


class SearchResult(TypedDict):
    matched: bool
    normalized_query: str


class RecursiveRecord(TypedDict, total=False):
    child: RecursiveRecord


if sys.version_info >= (3, 11):
    from typing import NotRequired, Required

    class MixedPresence(TypedDict, total=False):
        name: Required[str]
        note: NotRequired[Annotated[str, "Optional note"]]


@helix_tool(
    name="summarize_items",
    timeout=2,
    version="2026-07",
    tags=("math", "local", "math"),
)
def summarize(
    items: Annotated[list[int], "Values to summarize"],
    mode: Literal["sum", "max"] = "sum",
    pair: tuple[str, int] = ("items", 1),
    metadata: dict[str, bool] | None = None,
) -> dict[str, int | str]:
    """Summarize a list of integers."""

    del metadata
    value = sum(items) if mode == "sum" else max(items)
    return {"label": pair[0], "value": value}


def test_decorator_and_registry_compile_a_deterministic_contract() -> None:
    registry = ToolRegistry()
    spec = registry.register(summarize)

    assert spec.name == "summarize_items"
    assert spec.description == "Summarize a list of integers."
    assert spec.timeout == 2.0
    assert spec.tags == ("math", "local")
    assert spec.version == "2026-07"
    assert spec.is_async is False
    assert spec.input_schema["required"] == ["items"]
    assert spec.input_schema["additionalProperties"] is False
    assert spec.input_schema["properties"]["items"] == {
        "type": "array",
        "items": {"type": "integer"},
        "description": "Values to summarize",
    }
    assert spec.input_schema["properties"]["mode"]["enum"] == ["sum", "max"]
    assert spec.input_schema["properties"]["pair"]["prefixItems"] == [
        {"type": "string"},
        {"type": "integer"},
    ]
    assert spec.output_schema["type"] == "object"

    catalog = registry.schema_catalog()
    assert catalog["tools"] == [spec.to_dict()]
    assert registry.list() == (spec,)
    assert registry.get("summarize_items") == spec
    assert "summarize_items" in registry
    assert len(registry) == 1


def test_typed_dicts_compile_strict_named_nested_object_contracts() -> None:
    @helix_tool
    def search(request: SearchRequest) -> SearchResult:
        """Search a named area."""

        return {"matched": True, "normalized_query": request["query"].lower()}

    spec = ToolRegistry().register(search)
    request_schema = spec.input_schema["properties"]["request"]
    assert request_schema == {
        "type": "object",
        "properties": {
            "label": {"type": "string"},
            "limit": {"type": "integer"},
            "query": {"type": "string", "description": "Search phrase"},
            "coordinates": {
                "type": "object",
                "properties": {
                    "latitude": {
                        "type": "number",
                        "description": "Latitude in decimal degrees",
                    },
                    "longitude": {"type": "number"},
                },
                "required": ["latitude", "longitude"],
                "additionalProperties": False,
            },
        },
        "required": ["query", "coordinates"],
        "additionalProperties": False,
    }
    assert spec.output_schema == {
        "type": "object",
        "properties": {
            "matched": {"type": "boolean"},
            "normalized_query": {"type": "string"},
        },
        "required": ["matched", "normalized_query"],
        "additionalProperties": False,
        "$schema": "https://json-schema.org/draft/2020-12/schema",
    }


def test_typed_dict_required_and_not_required_qualifiers_are_respected() -> None:
    if sys.version_info < (3, 11):
        pytest.skip("stdlib Required and NotRequired were added in Python 3.11")

    @helix_tool
    def inspect_record(record: MixedPresence) -> bool:
        """Inspect a mixed-presence record."""

        return bool(record["name"])

    schema = ToolRegistry().register(inspect_record).input_schema["properties"]["record"]
    assert schema["required"] == ["name"]
    assert schema["properties"]["note"] == {
        "type": "string",
        "description": "Optional note",
    }


def test_recursive_typed_dict_contracts_are_rejected_at_declaration_time() -> None:
    with pytest.raises(ToolDefinitionError, match="Recursive TypedDict"):

        @helix_tool
        def inspect_recursive(record: RecursiveRecord) -> bool:
            """Inspect an unsupported recursive record."""

            return bool(record)


def test_samsarix_names_are_canonical_and_legacy_names_remain_compatible() -> None:
    import helix_core
    import samsarix_core

    assert samsarix_core.samsarix_tool is samsarix_core.helix_tool
    assert samsarix_core.SamsarixError is samsarix_core.HelixError
    assert helix_core.ToolRuntime is samsarix_core.ToolRuntime
    assert helix_core.ToolLifecycleEvent is samsarix_core.ToolLifecycleEvent
    assert helix_core.ToolLifecycleStatus is samsarix_core.ToolLifecycleStatus
    assert helix_core.ToolRateLimit is samsarix_core.ToolRateLimit
    assert helix_core.__version__ == samsarix_core.__version__


def test_registry_rejects_duplicates_and_supports_explicit_replace_and_remove() -> None:
    registry = ToolRegistry()
    first = registry.register(summarize)

    with pytest.raises(DuplicateToolError, match="already registered"):
        registry.register(summarize)

    assert registry.register(summarize, replace=True) == first
    assert registry.unregister("summarize_items") == first
    assert len(registry) == 0
    with pytest.raises(ToolNotFoundError):
        registry.get("summarize_items")
    with pytest.raises(ToolNotFoundError):
        registry.unregister("summarize_items")


def test_registry_capacity_is_bounded_but_replacement_and_reuse_are_allowed() -> None:
    @helix_tool(name="other")
    def other(value: int) -> int:
        """Return another value."""

        return value

    registry = ToolRegistry(max_tools=1)
    registry.register(summarize)

    with pytest.raises(RegistryCapacityError, match="capacity of 1"):
        registry.register(other)

    registry.register(summarize, replace=True)
    registry.unregister("summarize_items")
    assert registry.register(other).name == "other"


@pytest.mark.parametrize(
    ("value", "error"),
    [(0, ValueError), (-1, ValueError), (True, TypeError), (1.5, TypeError)],
)
def test_registry_capacity_configuration_is_validated(
    value: object, error: type[Exception]
) -> None:
    with pytest.raises(error):
        ToolRegistry(max_tools=value)  # type: ignore[arg-type]


def test_bare_decorator_uses_function_name_and_first_docstring_line() -> None:
    @helix_tool
    async def ping(enabled: bool) -> str | None:
        """Return a signal.

        Additional prose is deliberately not part of the short description.
        """

        return "pong" if enabled else None

    spec = ToolRegistry().register(ping)
    assert spec.name == "ping"
    assert spec.description == "Return a signal."
    assert spec.is_async is True
    assert spec.output_schema["anyOf"] == [{"type": "string"}, {"type": "null"}]


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: helix_tool(name="not valid"), "Tool names"),
        (lambda: helix_tool(timeout=0), "timeouts"),
        (lambda: helix_tool(version=" "), "versions"),
        (lambda: helix_tool(tags=("ok", "")), "tags"),
    ],
)
def test_invalid_metadata_is_rejected(factory: Any, message: str) -> None:
    def undecorated(value: int) -> int:
        """Return a value."""

        return value

    with pytest.raises(ToolDefinitionError, match=message):
        factory()(undecorated)


def test_missing_description_is_rejected() -> None:
    def undocumented(value: int) -> int:
        return value

    with pytest.raises(ToolDefinitionError, match="description"):
        helix_tool(undocumented)


def test_undecorated_callable_cannot_be_registered() -> None:
    def plain(value: int) -> int:
        """Return a value."""

        return value

    with pytest.raises(ToolDefinitionError, match="decorated"):
        ToolRegistry().register(plain)


def test_unsupported_function_contracts_fail_at_declaration_time() -> None:
    with pytest.raises(ToolDefinitionError, match="Parameter 'value'"):

        @helix_tool
        def missing_parameter_annotation(value) -> int:
            """Invalid."""

            return 1

    with pytest.raises(ToolDefinitionError, match="return type"):

        @helix_tool
        def missing_return(value: int):
            """Invalid."""

            return value

    with pytest.raises(ToolDefinitionError, match="calling convention"):

        @helix_tool
        def variadic(*values: int) -> int:
            """Invalid."""

            return sum(values)

    with pytest.raises(ToolDefinitionError, match="Any"):

        @helix_tool
        def untyped(value: Any) -> int:
            """Invalid."""

            return 1

    with pytest.raises(ToolDefinitionError, match="Default"):

        @helix_tool
        def bad_default(value: int = "one") -> int:  # type: ignore[assignment]
            """Invalid."""

            return value

    with pytest.raises(ToolDefinitionError, match="Generator"):

        @helix_tool
        def generator(value: int) -> list[int]:
            """Invalid."""

            yield value  # type: ignore[misc]


def test_literal_values_must_be_json_scalars() -> None:
    with pytest.raises(ToolDefinitionError, match="Literal values"):

        @helix_tool
        def invalid_literal(value: Literal[MARKER]) -> str:  # type: ignore[valid-type]
            """Invalid."""

            return str(value)

    with pytest.raises(ToolDefinitionError, match="Literal values"):

        @helix_tool
        def invalid_float_literal(value: Literal[math.inf]) -> str:  # type: ignore[valid-type]
            """Invalid."""

            return str(value)
