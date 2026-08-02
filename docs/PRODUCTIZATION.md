# Samsarix Core Productization Record

Last updated: 2026-08-01

## Current repository assessment

The repository began as a broad "unified agent runtime" containing orchestration,
reasoning, tool, metrics, and LLM-provider prototypes. The initial implementation
never formed an installable Python package, and later documentation described a
much larger product than the source actually supplied.

The strongest defensible independent product is a small, provider-neutral Python
runtime for defining, inspecting, and safely invoking application-owned tools. It
uses the existing decorator, registry, timeout, metrics, and async-execution ideas
without trying to reproduce the flagship `helix-unified` application or compete
with full agent frameworks.

### What worked at baseline

- The repository contained useful raw ideas for a decorator-based tool registry,
  async execution, timeouts, in-memory metrics, and response metadata.
- The source was Python-only and could become dependency-free at runtime.
- A source distribution and wheel could be built mechanically.

### What did not work at baseline

- `pip install .` failed because `helix-flow>=1.0.0` and
  `helix-circle>=1.0.0` were mandatory but unavailable from the configured
  package index.
- The built wheel was 5,206 bytes and contained only distribution metadata and
  the license; it contained no importable `helix_core` package.
- `import helix_core`, `import llm_providers`, and
  `python examples/basic_usage.py` all failed.
- `python -m pytest` collected 41 mock-oriented tests but produced 41 setup
  errors and 0% coverage because the repository-root `__init__.py` could not be
  imported as a package.
- Five advertised test modules were empty. The non-empty tests exercised
  `AsyncMock` fixtures instead of the implementation.
- The core dataclasses and their consumers disagreed about field names, status
  values, lifecycle methods, and result shapes.
- The README referenced missing requirements, docs, workflows, APIs, and an MIT
  license while the repository contains a Business Source License.
- No CI workflow existed at `HEAD`; the earlier workflow deliberately ignored
  lint and test failures.

## Chosen product definition

Samsarix Core is a lightweight, local-first Python tool runtime. It lets a developer:

1. mark a normal sync or async Python function as a tool;
2. register it under a stable name;
3. inspect a JSON-Schema-compatible input contract;
4. invoke it with validated arguments;
5. receive a structured success, validation, timeout, or failure result while
   normal caller cancellation propagates; and
6. run independent calls with an explicit concurrency bound.

The package does not choose an LLM provider or require an LLM. Its schemas and
result objects are suitable for adapters in agent frameworks, CLIs, bots, local
automation, or `helix-unified`.

## Target user and primary use case

The target user is a Python developer building an agent, workflow engine, bot, or
automation service who wants a small execution kernel without adopting a full AI
framework.

The primary release journey is:

`install -> decorate a typed function -> register it -> inspect its schema ->
invoke it -> handle the structured result`

This is independently useful because tool definition and execution are ordinary
application infrastructure, not a Samsarix-hosted service.

## Product and architecture decisions

- Use a conventional `src/samsarix_core` package layout so tests and builds exercise
  the installed package shape, with a lightweight `helix_core` compatibility import.
  The Python Packaging User Guide describes the src
  layout as a guard against accidentally importing repository-root files:
  <https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/>.
- Keep the first release free of runtime dependencies. The standard library is
  sufficient for signatures, JSON-compatible schemas, validation, async
  execution, timeouts, and metrics.
- Treat type hints and docstrings as the public tool contract. This matches current
  tool conventions in LangChain and Pydantic AI, while keeping Samsarix Core much
  smaller and provider-neutral:
  <https://docs.langchain.com/oss/python/langchain/tools> and
  <https://pydantic.dev/docs/ai/tools-toolsets/tools/>.
- Export conservative JSON-Schema-compatible object schemas and reject unknown
  arguments. JSON Schema Draft 2020-12 is the reference vocabulary:
  <https://json-schema.org/draft/2020-12>.
- Compile `TypedDict` into strict named object properties rather than representing
  heterogeneous records as a loose value union. MCP defines tool input/output
  contracts as JSON Schema objects, while Python exposes `is_typeddict` and
  semantic required/optional key introspection without a runtime dependency:
  <https://modelcontextprotocol.io/specification/2025-11-25/schema> and
  <https://docs.python.org/3/library/typing.html#typing.TypedDict>.
- Return structured results rather than swallowing errors or raising ordinary
  tool failures across the runtime boundary. Programmer/configuration errors may
  still raise during decoration or registration.
- Run synchronous functions in a worker thread. Timeouts bound the caller's wait,
  but cannot forcibly stop a Python thread; this limitation must remain explicit.
- Do not call in-process execution a sandbox. Registered tools retain the current
  process's filesystem, network, and environment permissions.
- Do not log tool arguments, return values, prompts, credentials, or user content
  by default.
- Do not ship the copied multi-provider LLM gateway as part of the supported
  package. Provider integration is a separate product concern with credentials,
  privacy, retries, pricing, and fast-moving model compatibility.

## Assumptions

- The repository owner wants an honest, independently useful extraction rather
  than a second copy of `helix-unified`.
- Python 3.10 remains the minimum supported version unless compatibility testing
  proves otherwise.
- The existing license text is owner-controlled. Engineering may correct metadata
  and documentation to describe it, but must not replace the license.
- Application code, not an untrusted end user, chooses which Python functions are
  registered. Tool arguments can still be untrusted and must be validated.

## Baseline command results

All baseline commands were run on Windows with Python 3.11.9 at commit
`69c9a2bc76ec700cb4bcf7af4286e24d75ea6667`.

| Command | Result |
| --- | --- |
| `python -m pip install .` in a new virtual environment | Failed: no matching distribution for `helix-flow>=1.0.0`; package not installed. |
| `python -m build --outdir <temp> <clean-copy>` | Exited 0, but produced a metadata-only 5,206-byte wheel with no `helix_core` package and emitted deprecated license-table warnings. |
| `python -c "import helix_core"` | Failed with `ModuleNotFoundError`. |
| `python -c "import llm_providers"` | Failed because `llm_providers.unified_llm` did not exist. |
| `python examples/basic_usage.py` | Failed because `helix_core` did not exist. |
| `python -m pytest` | Failed: 41 setup errors, 0% coverage, 70% threshold not met. |
| `python -m black --check .` | Failed: 20 files would be reformatted. |
| `python -m flake8 .` | Failed with extensive style and unused-code findings. |
| `python -m mypy . --ignore-missing-imports` | Failed: repository directory name was treated as an invalid package name. |

## Prioritized findings

### P0

- [x] Make a normal `pip install .` succeed without private or imaginary
  dependencies.
- [x] Ensure wheel and sdist contain the actual public package.
- [x] Make the documented primary journey runnable without credentials or network
  access.
- [x] Replace mock-only/broken tests with implementation tests and an installed
  wheel smoke test.
- [x] Restore CI that fails when meaningful checks fail.
- [x] Replace inaccurate README installation, API, maturity, CI, and license claims.

### P1

- [x] Validate invocation input, reject unknown arguments, and produce stable
  error contracts.
- [x] Support both sync and async tools with documented timeout and cancellation
  behavior.
- [x] Keep MCP cancellation responsive while bounding concurrently admitted stdio
  calls.
- [x] Bound parallel execution and retain input/result correlation.
- [x] Bound registry, batch, argument/output byte, nesting-depth, and value-node
  resources before executing untrusted calls.
- [x] Keep timed-out sync work observable and concurrency-bounded, and provide a
  finite-wait shutdown quiescence contract.
- [x] Remove the false "sandboxed execution" claim.
- [x] Eliminate unsafe `eval` examples from the active product documentation.
- [x] Isolate or remove obsolete provider, billing, pseudo-reasoning, and duplicate
  metrics implementations from the distributed package.
- [x] Prevent user-specific LLM responses from sharing a cache entry if the legacy
  gateway remains runnable anywhere in the tree.
- [x] Add `.gitignore` coverage for build, test, cache, and virtual-environment
  artifacts.
- [x] Configure one formatter/linter/type-check policy instead of incompatible
  defaults.

### P2

- [x] Add a dependency-free MCP adapter after stabilizing the core tool contract;
  prove it from an exact-pinned independent repository consumer.
- [ ] Add optional OpenAI-compatible, Anthropic, or agent-framework adapters only
  after consumer demand establishes a concrete contract.
- [ ] Add opt-in persistence for registry metadata and invocation summaries.
- [ ] Add process isolation for untrusted tools as a separate package or explicit
  execution backend.
- [x] Add strict named and nested `TypedDict` schemas after the first consumer
  exposed the ambiguity of heterogeneous `dict` results.
- [ ] Add richer schema support for dataclasses, enums, and constrained values if
  real adopters need it.

## Implementation checklist

- [x] Build the public `src/samsarix_core` API and legacy import compatibility layer.
- [x] Implement decoration, schema generation, registration, validation, execution,
  results, metrics, batch calls, lifecycle, timeout, and cancellation behavior.
- [x] Add a copy-pasteable offline example.
- [x] Add focused unit and integration tests, including the built wheel.
- [x] Add bounded development dependency ranges and deterministic tool configuration.
- [x] Add CI across supported Python versions.
- [x] Rewrite the README and contribution guidance around actual commands.
- [x] Complete the repository-wide threat model, candidate review, validation, and
  attack-path analysis.
- [x] Perform final clean install/build/test/lint/type-check/example verification.

## Release acceptance criteria

- A fresh virtual environment can install the repository with no private package
  index or credentials.
- The built wheel contains `samsarix_core` and the `helix_core` compatibility import,
  and works when installed outside the source tree.
- A new user can complete the primary journey from the README in under five
  minutes and entirely offline.
- Invalid, missing, extra, failed, timed-out, and cancelled invocations have tested
  behavior.
- Concurrency is bounded and tested.
- Formatting, linting, type checking, tests, package build, and example execution
  pass locally and in CI.
- Documentation contains no unsupported production, provider, benchmark, coverage,
  license, or security claims.
- No locally actionable P0 remains.

## Completed work

- Protected and inventoried the clean worktree before edits.
- Reviewed all 47 baseline files, recent history, local branches, removed CI, public
  APIs, tests, examples, configuration, and security-sensitive paths.
- Recorded real baseline install, build, import, example, test, format, lint, and
  type-check results.
- Performed bounded comparison against current official packaging, schema, and tool
  framework documentation.
- Selected the narrow standalone tool-runtime product wedge.
- Replaced the broken flat layout with the supported `src/samsarix_core` package,
  retained a narrow compatibility import, and archived the pre-2.0 prototypes
  outside the distribution.
- Implemented typed declaration, schema export, strict input/default/output
  validation, structured errors, redaction-by-default, bounded sync/async
  execution, batch ordering, cancellation, lifecycle, and content-free metrics.
- Added 27 real behavioral tests with a 90% branch-aware coverage gate, strict
  mypy, Ruff, Black, a Python 3.10-3.14 CI matrix, and pinned CI actions.
- Built the sdist and universal wheel and completed the offline example from an
  isolated wheel installation.
- Completed the repository threat model and closed five conservative security
  candidates with no reportable or deferred finding in the final worktree.
- Added the stable MCP 2025-11-25 tool lifecycle, structured output, behavioral
  annotations, client cancellation, and bounded concurrent local stdio transport
  without a runtime dependency.
- Added stable MCP progress notifications with invocation-scoped async reporting,
  strict monotonicity, update and UTF-8 message caps, cancellation cutoff, and
  custom-transport failure propagation.
- Added registry, batch, value-complexity, argument, and output resource budgets,
  plus observable bounded shutdown quiescence for timed-out synchronous work.
- Proved the public MCP API, exact typed result discovery, response-free
  asynchronous cancellation, and bounded content-free progress from
  `samsarix-integration-examples` 0.2.3 at merge commit
  `d8bf9c2b74a1b69ae39de16d449e674a66da7f44`; the consumer pins Core commit
  `beda0affe0dcc54c1a4e224bed26fbcd85e9184c`.

## Deferred work and rationale

P2 framework/provider adapters, registry persistence, process isolation, and richer
schema types remain deliberately deferred. They are not required for the first useful
release. One independent repository now proves the MCP boundary without needing those
features; subsequent surface area should follow concrete consumer demand. Core's own
[Python 3.10-3.14 hosted matrix](https://github.com/Deathcharge/samsarix-core/actions/runs/30727341629)
is green; Core's local Python 3.11 suite has 90 tests and 94.28% branch coverage.
The consumer's separate Python 3.11-3.13 jobs could not start because GitHub
reported an account billing/spending-limit problem, so its local 29-test and
installed-wheel evidence is recorded separately in `docs/ADOPTION.md`.

## Owner-, credential-, or production-blocked tasks

- Decide whether commercial licensing, paid support, or a service-level agreement
  will be offered separately from the MPL-2.0 community distribution. None is
  promised by this repository.
- Publishing to PyPI, signing a release, creating accounts, or deploying any service
  requires explicit owner authorization and is out of scope for this local pass.

## Known risks

- Python thread cancellation is cooperative; a timed-out synchronous function can
  continue in its worker thread. Its lifetime is now observable and waitable, but
  the function still needs its own deadline to guarantee eventual termination.
- In-process tools have the host process's permissions. This runtime is not suitable
  for arbitrary untrusted code without a separate isolation boundary.
- Type hints are not a complete runtime validation language. This alpha supports a
  documented JSON-compatible subset and rejects ambiguous usage.
- Exception redaction protects ordinary failures, but successful outputs and
  validation details still cross to the host by design.
- The MCP stdio adapter and runtime have per-message and per-invocation byte limits,
  but no request-rate, tenant-quota, connection, or aggregate-memory limit. Any
  remote host must apply those controls before invocation.
- Public package-index publication still requires owner-controlled credentials and
  an explicit release decision.

## Distribution and sustainability model

The simplest distribution is a pure-Python wheel and source distribution built
from GitHub tags, with no hosted service and no required API account. Operating
cost is therefore zero for the library itself; adopters pay only for infrastructure
or providers they choose outside Samsarix Core.

The unmodified MPL-2.0 license protects distributed changes to covered files while
allowing use in larger proprietary applications. Sustainability can come from paid
integration, support, hosted products, or separate commercial arrangements, but
none of those offerings or any revenue and demand claims are assumed here.
