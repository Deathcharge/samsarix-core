# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Type-hint compilation and strict invocation validation."""

from __future__ import annotations

import inspect
import json
import math
import types
from collections.abc import Callable, Iterator
from copy import deepcopy
from typing import Annotated, Any, Literal, Union, cast, get_args, get_origin, get_type_hints

from .errors import ToolArgumentError, ToolDefinitionError, ValidationIssue
from .models import JSONValue

_EMPTY = inspect.Signature.empty
_COMPACT_JSON_ENCODER = json.JSONEncoder(
    ensure_ascii=False,
    allow_nan=False,
    separators=(",", ":"),
)


def compile_tool_contract(
    function: Callable[..., Any],
) -> tuple[inspect.Signature, dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Compile a callable into a strict input and output JSON Schema contract."""

    if inspect.isgeneratorfunction(function) or inspect.isasyncgenfunction(function):
        raise ToolDefinitionError("Generator functions are not supported as tools")

    signature = inspect.signature(function)
    try:
        hints = get_type_hints(function, include_extras=True)
    except (NameError, TypeError) as exc:
        raise ToolDefinitionError(f"Could not resolve tool type hints: {exc}") from exc

    properties: dict[str, Any] = {}
    required: list[str] = []
    for parameter in signature.parameters.values():
        if parameter.kind in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            raise ToolDefinitionError(
                f"Parameter '{parameter.name}' uses an unsupported calling convention"
            )
        if parameter.name not in hints:
            raise ToolDefinitionError(f"Parameter '{parameter.name}' must have a type annotation")

        annotation = hints[parameter.name]
        parameter_schema = schema_for_type(annotation)
        if parameter.default is _EMPTY:
            required.append(parameter.name)
        else:
            try:
                normalized_default = validate_value(
                    parameter.default, annotation, path=f"$.{parameter.name}"
                )
                parameter_schema["default"] = to_json_value(normalized_default)
            except ToolArgumentError as exc:
                raise ToolDefinitionError(
                    f"Default for parameter '{parameter.name}' does not match its annotation"
                ) from exc
        properties[parameter.name] = parameter_schema

    if "return" not in hints:
        raise ToolDefinitionError("Tools must have a return type annotation")

    input_schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
    output_schema = schema_for_type(hints["return"])
    output_schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return signature, hints, input_schema, output_schema


def schema_for_type(annotation: Any) -> dict[str, Any]:
    """Return JSON Schema for the deliberately small supported type subset."""

    origin = get_origin(annotation)
    arguments = get_args(annotation)

    if origin is Annotated:
        base, *metadata = arguments
        schema = schema_for_type(base)
        description = next((item for item in metadata if isinstance(item, str)), None)
        if description:
            schema["description"] = description
        return schema
    if origin in {Union, types.UnionType}:
        return {"anyOf": [schema_for_type(item) for item in arguments]}
    if origin is Literal:
        if not arguments or any(not _is_json_scalar(item) for item in arguments):
            raise ToolDefinitionError("Literal values must be JSON scalars")
        return {"enum": list(arguments)}
    if annotation is str:
        return {"type": "string"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation in {None, type(None)}:
        return {"type": "null"}
    if origin is list:
        if len(arguments) != 1:
            raise ToolDefinitionError("list annotations must declare one item type")
        return {"type": "array", "items": schema_for_type(arguments[0])}
    if origin is tuple:
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return {"type": "array", "items": schema_for_type(arguments[0])}
        return {
            "type": "array",
            "prefixItems": [schema_for_type(item) for item in arguments],
            "minItems": len(arguments),
            "maxItems": len(arguments),
        }
    if origin is dict:
        if len(arguments) != 2 or arguments[0] is not str:
            raise ToolDefinitionError("dict annotations must use string keys and one value type")
        return {"type": "object", "additionalProperties": schema_for_type(arguments[1])}
    if annotation is Any:
        raise ToolDefinitionError("Any is not supported; use an explicit JSON-compatible type")
    raise ToolDefinitionError(f"Unsupported tool annotation: {annotation!r}")


def validate_arguments(
    signature: inspect.Signature,
    hints: dict[str, Any],
    arguments: Any,
) -> dict[str, Any]:
    """Validate keyword arguments without coercing unrelated scalar types."""

    if not isinstance(arguments, dict):
        raise ToolArgumentError(
            (
                ValidationIssue(
                    path="$",
                    code="invalid_arguments_object",
                    message="Arguments must be a dictionary with string keys",
                ),
            )
        )

    issues: list[ValidationIssue] = []
    parameters = signature.parameters
    for name in arguments:
        if not isinstance(name, str):
            issues.append(
                ValidationIssue(
                    path="$",
                    code="invalid_argument_name",
                    message="Argument names must be strings",
                )
            )
        elif name not in parameters:
            issues.append(
                ValidationIssue(
                    path=f"$.{name}",
                    code="unexpected_argument",
                    message=f"Unexpected argument '{name}'",
                )
            )

    validated: dict[str, Any] = {}
    for name, parameter in parameters.items():
        if name not in arguments:
            if parameter.default is _EMPTY:
                issues.append(
                    ValidationIssue(
                        path=f"$.{name}",
                        code="missing_argument",
                        message=f"Missing required argument '{name}'",
                    )
                )
            else:
                validated[name] = deepcopy(parameter.default)
            continue
        try:
            validated[name] = validate_value(arguments[name], hints[name], path=f"$.{name}")
        except ToolArgumentError as exc:
            issues.extend(exc.issues)

    if issues:
        raise ToolArgumentError(tuple(issues))
    return validated


def enforce_value_limits(
    value: Any,
    *,
    max_bytes: int,
    max_depth: int,
    max_nodes: int,
) -> None:
    """Reject cyclic, deeply nested, complex, or oversized JSON-like values.

    The traversal is iterative so hostile nesting cannot exhaust Python's call
    stack before the ordinary annotation validator runs. The root is depth zero;
    each container and scalar counts as one node, while object keys do not.
    """

    nodes = 0
    active_containers: set[int] = set()
    stack: list[tuple[str, Any, int]] = [("value", value, 0)]

    while stack:
        operation, current, depth = stack.pop()
        if operation == "exit":
            active_containers.remove(current)
            continue
        if operation == "children":
            children = cast(Iterator[Any], current)
            try:
                child = next(children)
            except StopIteration:
                continue
            stack.append(("children", children, depth))
            stack.append(("value", child, depth))
            continue

        nodes += 1
        if nodes > max_nodes:
            raise _value_error(
                "$",
                "value_too_complex",
                f"Value exceeds the configured limit of {max_nodes} nodes",
            )
        if depth > max_depth:
            raise _value_error(
                "$",
                "value_too_deep",
                f"Value exceeds the configured nesting depth of {max_depth}",
            )

        if isinstance(current, (list, tuple, dict)):
            identity = id(current)
            if identity in active_containers:
                raise _value_error("$", "cyclic_value", "Values must not contain cycles")
            active_containers.add(identity)
            stack.append(("exit", identity, depth))
            children = iter(current.values()) if isinstance(current, dict) else iter(current)
            stack.append(("children", children, depth + 1))

    encoded_bytes = 0
    try:
        for chunk in _COMPACT_JSON_ENCODER.iterencode(value):
            encoded_bytes += len(chunk.encode("utf-8"))
            if encoded_bytes > max_bytes:
                raise _value_error(
                    "$",
                    "value_too_large",
                    f"Value exceeds the configured JSON size of {max_bytes} bytes",
                )
    except ToolArgumentError:
        raise
    except (RecursionError, TypeError, ValueError) as exc:
        raise _value_error("$", "not_json_compatible", "Value must be JSON-compatible") from exc


def validate_value(value: Any, annotation: Any, *, path: str) -> Any:
    """Validate one value and normalize tuples to their annotated Python form."""

    origin = get_origin(annotation)
    arguments = get_args(annotation)

    if origin is Annotated:
        return validate_value(value, arguments[0], path=path)
    if origin in {Union, types.UnionType}:
        for option in arguments:
            try:
                return validate_value(value, option, path=path)
            except ToolArgumentError:
                continue
        raise _value_error(path, "union_mismatch", "Value does not match any allowed type")
    if origin is Literal:
        if any(type(value) is type(item) and value == item for item in arguments):
            return value
        raise _value_error(path, "literal_mismatch", f"Value must be one of {list(arguments)!r}")
    if annotation is str:
        if isinstance(value, str):
            return value
        raise _type_error(path, "string")
    if annotation is bool:
        if isinstance(value, bool):
            return value
        raise _type_error(path, "boolean")
    if annotation is int:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        raise _type_error(path, "integer")
    if annotation is float:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            number = float(value)
            if math.isfinite(number):
                return number
        raise _type_error(path, "finite number")
    if annotation in {None, type(None)}:
        if value is None:
            return None
        raise _type_error(path, "null")
    if origin is list:
        if not isinstance(value, list):
            raise _type_error(path, "array")
        return [
            validate_value(item, arguments[0], path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if origin is tuple:
        if not isinstance(value, (list, tuple)):
            raise _type_error(path, "array")
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return tuple(
                validate_value(item, arguments[0], path=f"{path}[{index}]")
                for index, item in enumerate(value)
            )
        if len(value) != len(arguments):
            raise _value_error(
                path,
                "tuple_length",
                f"Expected {len(arguments)} items but received {len(value)}",
            )
        return tuple(
            validate_value(item, item_type, path=f"{path}[{index}]")
            for index, (item, item_type) in enumerate(zip(value, arguments, strict=True))
        )
    if origin is dict:
        if not isinstance(value, dict):
            raise _type_error(path, "object")
        if any(not isinstance(key, str) for key in value):
            raise _value_error(path, "invalid_object_key", "Object keys must be strings")
        return {
            key: validate_value(item, arguments[1], path=f"{path}.{key}")
            for key, item in value.items()
        }
    raise ToolDefinitionError(f"Unsupported tool annotation: {annotation!r}")


def to_json_value(value: Any) -> JSONValue:
    """Normalize a value to strict JSON data or raise a safe validation error."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        raise ToolArgumentError(
            (ValidationIssue("$", "non_finite_number", "Numbers must be finite"),)
        )
    if isinstance(value, (list, tuple)):
        return [to_json_value(item) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ToolArgumentError(
                (ValidationIssue("$", "invalid_object_key", "Object keys must be strings"),)
            )
        return {key: to_json_value(item) for key, item in value.items()}
    raise ToolArgumentError(
        (ValidationIssue("$", "not_json_compatible", "Value must be JSON-compatible"),)
    )


def _is_json_scalar(value: Any) -> bool:
    return (
        value is None
        or isinstance(value, (str, bool, int))
        or (isinstance(value, float) and math.isfinite(value))
    )


def _type_error(path: str, expected: str) -> ToolArgumentError:
    return _value_error(path, "type_mismatch", f"Expected {expected}")


def _value_error(path: str, code: str, message: str) -> ToolArgumentError:
    return ToolArgumentError((ValidationIssue(path=path, code=code, message=message),))
