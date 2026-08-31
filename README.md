# Samsarix Core

[![CI](https://github.com/Deathcharge/samsarix-core/actions/workflows/ci.yml/badge.svg)](https://github.com/Deathcharge/samsarix-core/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](pyproject.toml)
[![License: MPL-2.0](https://img.shields.io/badge/License-MPL--2.0-brightgreen.svg)](LICENSE)

Samsarix Core is a small, dependency-free Python runtime from
[Samsarix LLC](https://samsarix.com) for declaring typed local tools and invoking
them through one predictable async API.

This `2.0` line is an honest alpha: the primary workflow is implemented and
tested, but the API and distribution are not yet declared stable. It does not
provide an LLM, agent loop, plugin marketplace, network service, authentication,
persistence, or an untrusted-code sandbox.

## What it does

- turns annotated sync or async functions into inspectable tool contracts;
- emits JSON Schema Draft 2020-12 input and output schemas;
- validates arguments and outputs without surprising scalar coercion;
- returns structured success, validation, policy-denial, overload, rate-limit,
  open-circuit, timeout, missing-tool, and failure results;
- bounds pending invocations, registry growth, batches, value size/complexity,
  global and per-tool concurrent work, sustained per-tool request rate, repeated
  calls to failing dependencies, and thread-pool use;
- supports ordered batch invocation and cooperative async cancellation;
- optionally requires a bounded host-owned policy decision after validation and
  before any tool code executes;
- keeps metrics content-free and redacts exception messages by default;
- optionally emits provider-neutral, content-free invocation lifecycle events for
  tracing and service-level indicators;
- exposes the same contracts through a dependency-free, cancellable,
  progress-aware, operationally observable, and admission-bounded MCP stdio bridge;
- optionally exposes long-running tools through the experimental MCP task lifecycle
  with bounded in-memory retention, polling, deferred results, and cancellation.

Samsarix Core is local and provider-neutral. It has no runtime dependencies, no
accounts, no API keys, no external service, and no hosted operating cost.

## Install

Python 3.10 or newer is required.

The latest published immutable prerelease is
[`v2.0.0a10`](https://github.com/Deathcharge/samsarix-core/releases/tag/v2.0.0a10),
with an installable wheel, source distribution, SHA-256 manifest, and verifiable
GitHub Actions build provenance. A compact verified-wheel path is:

```bash
gh release download v2.0.0a10 --repo Deathcharge/samsarix-core --pattern "*.whl"
gh attestation verify samsarix_core-2.0.0a10-py3-none-any.whl \
  --repo Deathcharge/samsarix-core \
  --signer-workflow Deathcharge/samsarix-core/.github/workflows/release.yml \
  --source-ref refs/tags/v2.0.0a10 \
  --source-digest e4d0ed3a85a65a2f3e11a02e2f744f42ca0e5c4a \
  --deny-self-hosted-runners &&
python -m pip install samsarix_core-2.0.0a10-py3-none-any.whl
```

Version `2.0.0a10` adds opt-in modern MCP ordinary-tool support while preserving
the default 2025 protocol. The freshly downloaded release wheel passed the offline
runtime, MCP subprocess and SQLite transaction/replay gate, plus official MCP SDK
1.29.1 legacy, 2.1.1 legacy and 2.1.1 modern journeys with cancellation recovery.
It includes the a9 diagnostic, numeric-overflow and malformed-frame fixes. Older
releases do not gain new APIs from being rechecked with newer verification scripts.

For a source checkout instead:

```bash
python -m pip install .
```

For development:

```bash
python -m pip install -e ".[dev]"
```

The project is not represented here as a published PyPI release. Approved version tags
use a fail-closed GitHub release workflow with strict metadata checks, clean-wheel smoke
tests, SHA-256 manifests, provenance attestations, and immutable assets. See the
[release process and evidence](docs/RELEASING.md).

## One complete example

```python
import asyncio
from typing import Literal

from samsarix_core import ToolRuntime, samsarix_tool


@samsarix_tool(timeout=2, tags=("demo",))
def convert_temperature(
    value: float,
    to: Literal["celsius", "fahrenheit"],
) -> dict[str, float | str]:
    """Convert a temperature to the requested unit."""

    converted = value * 9 / 5 + 32 if to == "fahrenheit" else (value - 32) * 5 / 9
    return {"unit": to, "value": round(converted, 2)}


async def main() -> None:
    async with ToolRuntime(max_concurrency=4) as runtime:
        runtime.register(convert_temperature)

        print(runtime.registry.schema_catalog())
        result = await runtime.invoke(
            "convert_temperature",
            {"value": 20, "to": "fahrenheit"},
        )
        print(result.to_dict())


asyncio.run(main())
```

For a fail-closed request-local capability example, run
`python examples/policy_gate.py`. A host policy receives a detached, validated call
snapshot and returns `ToolPolicyDecision.ALLOW` or `DENY`; it is not an authentication
service or a durable human-approval workflow.

That example is a preview. For actual transactional writes, duplicate-request handling,
and replay after restart, run `python examples/sqlite_reservations.py`. It uses a fresh
temporary SQLite database and verifies that five items become three only once. See
the [side-effect and replay guide](docs/SIDE_EFFECTS.md) before adapting it to real data.

For a quota-constrained dependency with safe retry handling, run
`python examples/rate_limited_api.py`.
For a failing dependency with fail-fast recovery probing, run
`python examples/circuit_breaker_api.py`.

## Connect an MCP client

Samsarix Core implements the stable MCP tool lifecycle, discovery, invocation,
structured output, behavioral annotations, progress notifications, and client
cancellation without adding an SDK dependency. Opt-in operational logging emits
content-free terminal events at the minimum level selected by the client. Concurrent
stdio calls are separately admission-bounded so protocol work is capped before it
reaches the runtime's own pending-invocation limit. Experimental MCP task execution
is disabled by default; the included inventory server enables it for one
progress-reporting audit tool while
retaining normal calls for clients that do not support tasks. A complete server is included:

```bash
python examples/mcp_inventory_server.py
```

Configure that command in a trusted local MCP client to discover and call the
decorated tools. See the [MCP bridge guide](docs/MCP.md) for lifecycle support,
read/write/destructive annotations, scalar-output wrapping, cancellation, stdio
progress and logging, bounded task retention, admission limits, and security boundaries.

Starting with `2.0.0a10`, Core additionally supports an opt-in `2026-07-28` ordinary-tool
path: launch the example with `--modern`, or use `MCPServer(runtime,
enable_modern=True)`. It supplies per-request version/capability validation,
discovery, private cache hints and request-scoped logging without the legacy
handshake. This option is included in the published a10 wheel, not a9. See the
[modern protocol boundary](docs/MCP.md#opt-in-mcp-2026-07-28); the redesigned task
extension, multi-round-trip operations and HTTP are not implemented.

## Proven external consumer

[Samsarix Integration Examples](https://github.com/Deathcharge/samsarix-integration-examples)
version 0.2.12 pins Core commit `2744d69eb58aef8412d15fbee9485b6d22eb30a5`
and uses only the
public API to expose a privacy-first, resumable redaction workflow over MCP. Its
consumer-owned tests exercise initialization, discovery, stdio invocation,
structured results, privacy boundaries, path traversal and linked-file refusal,
artifact conflict handling, exact `TypedDict` output discovery, client
cancellation without an output artifact or response, continued protocol service,
token-correlated content-free progress, client-filtered operational logging,
synchronous timeout/quiescence accounting, package installation, and CLI entry points.
It also proves the experimental task lifecycle on the real redaction workflow:
immediate private task state, status polling, blocking result retrieval, related-task
progress, safe cancellation, bounded retention, and unavailable unauthenticated listing.
Its fail-closed host policy also admits only the exact validated redaction contract and
denies an independently registered destructive, open-world tool before execution without
reflecting that tool's private argument.
It separately saturates Core's direct-runtime admission cap and proves MCP returns a
retryable, content-free overload result without another policy evaluation, tool
execution, retained private arguments, or an output artifact.
Its host-owned lifecycle handler also receives correlated `started` and `success`
events for the real policy-gated redaction call while consumer tests prove that source
secrets, filenames, output names, run IDs, and workspace paths never enter the event
stream.
The same adapter can opt into a Core token bucket for that exact registration. Its
consumer-owned test proves one policy-gated redaction succeeds, an immediate second call
returns a safe retryable `rate_limited` result, no second artifact is created, and the
content-free success and rate-limit metrics each increment exactly once.
The adapter independently accepts a host-owned circuit breaker. Its consumer-owned
test injects one private downstream failure, proves the next call fails fast without
tool execution, artifact creation, or private protocol content, then completes one
real half-open recovery redaction and closes the circuit with exact aggregate metrics.
The preceding v0.2.6 contract was also discovered and invoked through official MCP
Inspector 0.21.2; a portable VS Code workspace is configuration-discovered, with
signed-in trust and tool approval still awaiting operator acceptance.

This is compatibility evidence, not a claim of third-party production adoption.
See the [adoption record](docs/ADOPTION.md) for exact commits, commands, artifact
digests, limitations, and rollback.

The distribution name is `samsarix-core`. The former `helix_core` import,
`helix_tool` decorator, and `HelixError` base class remain compatibility aliases
for existing prototypes; new code should use the Samsarix names above.

The decorator rejects ambiguous definitions early. Every parameter and return
value needs a supported type annotation, and every tool needs a description or
docstring. Supported types are `str`, `bool`, `int`, finite `float`, `None`,
`Literal`, unions/optionals, typed `list`, typed `tuple`, and `dict[str, T]`.
`TypedDict` adds strict named nested objects, and
`Annotated[T, "description"]` adds a property description to the schema.

## Runtime contract

`ToolRuntime.invoke()` never turns an ordinary tool failure into an uncaught
exception. It returns a `ToolResult` with one of these states:

- `success`
- `not_found`
- `invalid_arguments`
- `denied`
- `busy`
- `rate_limited`
- `circuit_open`
- `timed_out`
- `failed`
- `runtime_closed`

Caller cancellation is different: `asyncio.CancelledError` propagates so normal
structured-concurrency semantics keep working.

`expose_exceptions=False` is the default. Failure results include the exception
class but not its message or traceback. Enable exception messages only in a
trusted local debugging context.

An optional async `ToolRuntime(policy=...)` gate runs after argument validation and
before sync or async tool execution. Policy denials and policy failures never expose
the call snapshot in results; malformed policy output and policy exceptions fail
closed. Evaluation is concurrency-bounded, and the invocation timeout and caller
cancellation include policy waiting and execution.

The runtime also rejects oversized, cyclic, deeply nested, or overly complex
arguments before a tool runs. Output-limit failures are redacted structured
results. See the [API reference](docs/API_REFERENCE.md) for the defaults and tune
them to the host's actual workload.

Hosts can isolate a slow or quota-constrained dependency when registering its tool:

```python
from samsarix_core import ToolCircuitBreaker, ToolRateLimit

runtime = ToolRuntime(max_concurrency=8)
runtime.register(
    query_warehouse,
    max_concurrency=2,
    rate_limit=ToolRateLimit(calls=60, period_seconds=60, burst=5),
    circuit_breaker=ToolCircuitBreaker(
        failure_threshold=3,
        recovery_timeout_seconds=30,
    ),
)
runtime.register(health_check)
```

The per-tool slot is acquired before the global execution slot, so queued warehouse
calls cannot consume all eight slots and starve `health_check`. The same deployment-local
limit covers direct, batch, MCP, and MCP task calls without becoming discoverable tool
metadata. The invocation timeout includes bulkhead waiting, and the overall
`max_pending_invocations` cap still bounds every waiter.
The independent token bucket admits five warehouse starts before any refill is needed
and then refills at one call per second; `max_concurrency=2` still permits at most two
warehouse calls to execute concurrently. An empty bucket returns retryable status
`rate_limited` with a safe `retry_after_ms` hint and never runs the tool. The bucket is
process-local deployment policy, not tenant fairness or a distributed quota service. See
[per-tool rate limits](docs/RATE_LIMITS.md).

The circuit breaker counts consecutive tool/output failures and caller-visible
timeouts. Once open, it rejects before capacity or tokens are consumed, then admits one
half-open recovery probe after 30 seconds. Invalid input, host policy outcomes,
admission/rate rejections, progress-handler failure, and caller cancellation do not
trip it. Core does not automatically retry calls. Breaker state is process-local
deployment policy and can be inspected or manually reset by the host. See
[per-tool circuit breakers](docs/CIRCUIT_BREAKERS.md).

Hosts can attach a synchronous `lifecycle_handler` to receive paired, immutable start
and terminal events across direct, batch, MCP, and task calls. Events contain only
invocation ID, requested tool name, status, UTC time, and terminal duration; arguments,
outputs, exception text, policy context, and progress text are never copied. Exporter
failures are isolated and counted. See [Lifecycle observability](docs/OBSERVABILITY.md)
for delivery semantics, privacy/cardinality cautions, and a content-free OpenTelemetry
`execute_tool` adapter.

## Important boundaries

- Registered functions are trusted application code and run in the current process.
  Registration is not a security sandbox.
- Async timeouts cancel the running coroutine when it cooperates with cancellation.
- A timed-out sync function may keep running in its worker thread. The pool stays
  bounded and its global and per-tool concurrency slots stay occupied until it actually stops. Inspect
  `pending_sync_calls`, or use `wait_for_sync()` / `aclose(wait_for_sync=True)` when
  shutdown must prove quiescence. The function still needs its own I/O deadlines.
- Opt-in MCP tasks are experimental and session-local. Their finite TTL limits
  result access; lazy cleanup is not a timed physical-memory erasure guarantee.
  There is no durable queue, restart recovery, or unauthenticated task listing.
- Tool outputs are returned to the caller. Do not return secrets to an untrusted
  model, client, or log sink.
- A policy is application code, not caller authentication or user consent. Keep MCP
  confirmation in the client and durable pause/approve/resume state in the outer agent
  or workflow.
- Use one runtime within one event-loop lifecycle; close it with `async with` or
  `await runtime.aclose()`. The default close is non-blocking for surviving sync
  threads and reports whether they are already quiescent.

See [Getting started](docs/GETTING_STARTED.md), the [API reference](docs/API_REFERENCE.md),
[architecture](docs/ARCHITECTURE.md), [MCP bridge](docs/MCP.md),
[lifecycle observability](docs/OBSERVABILITY.md), [best practices](docs/BEST_PRACTICES.md),
[per-tool rate limits](docs/RATE_LIMITS.md), [per-tool circuit breakers](docs/CIRCUIT_BREAKERS.md),
[benchmark guide](docs/BENCHMARKS.md),
the [adoption record](docs/ADOPTION.md), and the [productization
record](docs/PRODUCTIZATION.md).

## Quality status

The release gate runs Black, Ruff, strict mypy, and the test suite with at least 90%
branch-aware coverage on Python 3.10–3.14. Package CI builds and installs the wheel
offline on Linux, Windows, and macOS at Python 3.10 and 3.14, then exercises real
runtime invocation/circuit recovery and the documented MCP server through subprocess
pipes. Reproduce that gate with `python scripts/verify_distribution.py path/to/wheel.whl`;
see [release verification](docs/RELEASING.md) for scope and isolation details.

A separate [official MCP client gate](docs/MCP.md#official-python-client-verification)
tests SDK versions 1.29.1 and 2.1.1 on Linux, Windows and macOS. It runs the server
from an isolated Core-only wheel installation and verifies the supported
`2025-11-25` tool journey, including 2.x automatic negotiation fallback and repeated
cooperative cancellation with execution-slot recovery. SDK 1.x needs an explicit
cancellation notification; the tested 2.x client sends it automatically. This does
not claim newer protocol support, experimental-task interoperability or signed-in
client approval. The SDK is a test-only dependency, not part of Core.

Run `python benchmarks/runtime_benchmark.py` or
`python benchmarks/mcp_stdio_benchmark.py` for machine-readable local
microbenchmarks. They are comparison aids, not universal performance claims or CI
speed thresholds.

## Support and contact

- Company website: [samsarix.com](https://samsarix.com)
- Product and partnership questions: `contact@samsarix.com`
- Technical support and conduct reports: `support@samsarix.com`
- Bugs and feature requests: [GitHub Issues](https://github.com/Deathcharge/samsarix-core/issues)

This project is maintained by Samsarix LLC. Support is currently best-effort and
does not include a service-level agreement.

## License and trademarks

Samsarix Core is licensed under the [Mozilla Public License 2.0](LICENSE). Changes
to covered source files that are distributed must remain available under the MPL,
while the files may be combined with differently licensed larger works.

Copyright 2026 Samsarix LLC. See [NOTICE](NOTICE) for ownership and attribution
information, [CITATION.cff](CITATION.cff) for citation metadata, and
[TRADEMARKS.md](TRADEMARKS.md) for use of Samsarix names and marks.

Security reports should follow [SECURITY.md](SECURITY.md). Contributions should
follow [CONTRIBUTING.md](CONTRIBUTING.md).
