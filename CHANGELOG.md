# Changelog

## Unreleased

### Added

- public SQLite MCP reservation launcher using the existing application-owned store:
  explicit initialization, read-only defaults, host write opt-in, bounded ledger,
  both protocol eras and durable replay across server processes;
- installed-wheel real-process and independent disk-state verification for that
  workflow, plus host-policy, CLI, schema-startup and checker negative controls.

### Changed

- recorded immutable `v2.0.0a10` assets, exact-source provenance and fresh offline
  and official-client verification; updated installation and adoption guidance
  without implying a separate-consumer upgrade or stable release.
- identify the existing consumer as private and same-owner; record the unsuppressed
  37-pass/one-old-version-failure a10 candidate qualification separately from adoption.
- exclude application-owned SQLite data and sidecars from Git and source archives.

## 2.0.0a10 - 2026-08-31

### Added

- opt-in MCP `2026-07-28` stdio tool support with per-request metadata, discovery,
  version errors, complete-result/server identity fields, private zero-TTL catalog
  hints, per-request operational-log filtering and cooperative cancellation;
  preserve the default 2025 contracts and reject unsupported modern continuations.
- independent SDK 2.1.1 installed-wheel modern-mode verification, including
  discovery without fallback and repeated cancellation, in all three OS CI jobs.
- official-client cooperative cancellation/recovery verification: SDK 1.29.1 uses
  an explicit typed notification with an observed request ID, while SDK 2.1.1
  sends cancellation automatically; a controlled single-slot fixture and negative
  controls distinguish server cleanup from local cancellation, timeout or early completion.
- independent installed-wheel verification with official MCP Python SDK 1.29.1
  and 2.1.1, including current-client negotiation fallback, parsed schema/results,
  Unicode, private-input redaction, logging and progress; six cross-platform CI
  jobs and negative controls with bounded checker cleanup and an independent
  test-server lifetime watchdog.

### Changed

- make cancellation verification wait for bounded terminal-counter convergence
  after execution-slot release; a reproduced scheduling race is not mistaken for
  a leak, while negative controls still reject missing cancellation or stuck counters.
- recorded immutable `v2.0.0a9` assets, exact-source provenance, fresh installed-wheel
  checks, and tag-ref build-only dispatch evidence; updated installation instructions
  while keeping older consumer evidence and remaining adoption gates explicit.
- describe MCP support by explicit protocol revision instead of the stale claim
  that the implemented revision is current; distinguish ordinary tool compatibility
  from experimental tasks and newer protocol features.

## 2.0.0a9 - 2026-08-31

### Fixed

- bound derived validation diagnostics to 64 issues (including a truncation marker)
  and 128 characters per path/message, preventing long dictionary keys from being
  multiplied into unbounded nested errors; preserve ordinary error paths and valid
  union alternatives;
- convert overflowing float arguments into ordinary validation errors, preserve
  ordered mixed-batch results, and normalize default/output contract failures;
- reject array/object MCP methods without terminating stdio, safely serialize lone
  surrogate metadata, and enforce the response cap on fallback frames and delimiters;
- restrict release publication and attestation to tag-push events, keeping manual
  dispatches build-only even when targeting a tag; clarify lazy task TTL cleanup.

### Added

- bounded diagnostic/numeric and malformed-frame regression checks in the offline
  installed-wheel gate, including real MCP subprocess pipes and checker negative controls.

### Changed

- recorded immutable `v2.0.0a8` assets, checksums, exact-source provenance and fresh
  installed-wheel verification; updated the published installation path.

## 2.0.0a8 - 2026-08-31

### Fixed

- reject NaN, infinite and overflowing execution timeouts consistently at decorator,
  runtime-default and invocation boundaries; invalid overrides return a safe result
  without consuming admission or aborting valid batch items;
- validate sync-wait/shutdown timeouts before closing or cancelling active work,
  preserving explicit unbounded `None` and zero-duration polling;
- reject overflowing MCP task TTLs as invalid parameters rather than internal errors,
  and reject unrepresentable host task-duration settings before task-store use.

### Added

- application-owned SQLite reservation example with atomic stock/ledger commits,
  bounded request retention, replay and conflicting-key semantics, concurrency,
  rollback and lost-response regression tests, and offline installed-wheel coverage;
- bounded mixed-dependency outage benchmark comparing global concurrency, per-tool
  isolation, and circuit breaking, with repeated raw measurements, correctness and
  cleanup regression tests, and explicit synthetic-workload limitations;
- portable offline installed-wheel verification for actual runtime invocation,
  validation, ordered batches, circuit recovery, and real MCP subprocess Unicode,
  progress, logging and EOF behavior, with checker regression tests;
- Linux, Windows and macOS package CI at Python 3.10 and 3.14.

### Changed

- explicitly label the policy-gate reservation as a preview rather than a real write;
- corrected the a7 import-only smoke's overstated behavioral evidence and reverified
  the unchanged published wheel with the earlier expanded gate; the later deadline
  gate correctly rejects a7 and is required for this release;
- recorded immutable `v2.0.0a7` release checksums, provenance, and clean
  installed-wheel circuit-breaker recovery evidence.

## 2.0.0a7 - 2026-08-11

### Added

- opt-in process-local per-tool consecutive-failure circuit breakers with safe
  fail-fast results, one half-open recovery probe, queued-permit invalidation,
  manual inspection/reset, content-free metrics/lifecycle events, and consistent
  direct, batch, MCP, and task behavior.

### Changed

- recorded independent consumer `0.2.12` adoption evidence for the process-local
  per-tool circuit-breaker contract.
- recorded immutable `v2.0.0a6` release checksums, provenance, and clean
  installed-wheel rate-limit recovery evidence.

## 2.0.0a6 - 2026-08-10

### Added

- opt-in process-local per-tool token buckets with explicit sustained rate and
  burst capacity, safe retry delays, content-free rejection metrics and lifecycle
  events, and consistent direct, batch, MCP, and task behavior.

### Changed

- recorded independent consumer `0.2.11` adoption evidence for the process-local
  per-tool rate-limit contract.
- recorded immutable `v2.0.0a5` release checksums, provenance, and clean installed-wheel
  lifecycle evidence.

## 2.0.0a5 - 2026-08-02

### Added

- opt-in provider-neutral lifecycle observability with paired immutable start/terminal
  events, explicit cancellation/abort states, content-free payloads, isolated handler
  failures, and an OpenTelemetry `execute_tool` adapter.

### Changed

- recorded independent consumer `0.2.10` adoption evidence for the content-free
  lifecycle-observability contract.
- recorded immutable `v2.0.0a4` release checksums, provenance, and clean installed-wheel
  bulkhead evidence.

## 2.0.0a4 - 2026-08-02

### Added

- deployment-local per-tool execution bulkheads through
  `ToolRuntime.register(..., max_concurrency=N)`, with tool-first semaphore ordering,
  bounded waiting, timeout/cancellation integration, and retained slots for surviving
  synchronous work; mixed-batch workers use pending capacity so constrained-tool waits
  do not head-of-line block unrelated tools.

### Changed

- recorded immutable `v2.0.0a3` release provenance and independent consumer `0.2.9`
  adoption evidence for the bounded runtime-admission contract.

## 2.0.0a3 - 2026-08-02

### Changed

- made CI and release-wheel compatibility checks compare the `helix_core` namespace
  against the built package version instead of a release-specific literal.

## 2.0.0a2 - 2026-08-02

### Added

- bounded direct-runtime admission with fail-fast, retryable `runtime_busy` results,
  content-free current/peak/rejection metrics, batch-aware worker sizing, and MCP
  serialization coverage.

### Release status

- the immutable `v2.0.0a2` tag failed closed during wheel smoke testing before
  attestation or publication; it has no GitHub release and is superseded by
  `v2.0.0a3`.

### Changed

- recorded the immutable `v2.0.0a1` GitHub prerelease, published artifact digests,
  build-provenance verification, and clean release-wheel installation evidence.

## 2.0.0a1 - 2026-08-02

This is a replacement alpha rather than a compatibility release.

### Added

- dependency-free typed sync/async tool declarations;
- JSON Schema Draft 2020-12 contract export;
- strict named and nested object contracts from `TypedDict`, including inherited
  totality and `Required`/`NotRequired` presence qualifiers when available;
- strict argument/default/output validation;
- structured results with exception redaction by default;
- bounded concurrency, a private sync thread pool, timeouts, cancellation, and
  ordered batch invocation;
- content-free runtime metrics;
- opt-in bounded async invocation policy with detached validated context, explicit
  allow/deny decisions, safe fail-closed errors, and direct/batch/MCP/task coverage;
- configurable registry, batch, argument/output byte, nesting-depth, and value-node
  limits with safe structured failures;
- observable timed-out sync work, retained concurrency slots, late-failure draining,
  and optional bounded shutdown quiescence;
- dependency-free MCP `2025-11-25`/`2025-06-18` lifecycle, tool discovery,
  invocation, structured results, behavioral annotations, and bounded stdio;
- MCP client cancellation for active tool calls, concurrent stdio dispatch, and
  configurable in-flight request admission;
- invocation-scoped async progress reporting with strict ordering, resource caps,
  MCP progress-token correlation, and notification-before-response delivery;
- opt-in MCP operational logging with capability negotiation, client-selected
  minimum levels, one content-free terminal event per non-cancelled call, and
  best-effort delivery;
- opt-in experimental MCP task-augmented tool execution with per-tool negotiation,
  secure task IDs, bounded finite retention, polling, blocking result retrieval,
  cancellation, related-task metadata, and old-client compatibility;
- formatter, linter, and strict type-check coverage for the shipped examples and
  benchmark programs;
- independently packaged consumer evidence for progress-token correlation,
  notification ordering, protocol privacy, and cancellation cutoff;
- independently packaged consumer evidence for client-filtered content-free MCP
  operational logging;
- independently packaged consumer evidence for retained synchronous worker capacity
  after timeout and bounded shutdown quiescence;
- official MCP Inspector installed-wheel invocation and Visual Studio Code workspace
  configuration-discovery evidence from the independent consumer;
- independently packaged redaction evidence for experimental task creation, status,
  blocking result retrieval, related-task progress, bounded retention, cancellation,
  and private task state;
- independently packaged redaction evidence for the invocation-policy allow path and
  safe denial of an out-of-contract tool before execution;
- tag-gated GitHub release automation with tag/version enforcement, strict metadata and
  clean-wheel checks, checksums, build-provenance attestations, and immutable-release
  operating guidance;
- real behavioral tests, strict typing/linting, package smoke tests, and accurate docs;
- a dependency-free JSON runtime microbenchmark for repeatable local comparisons.
- a dependency-free MCP stdio microbenchmark covering parsing, dispatch,
  validation, execution, and response serialization.

### Changed

- packaging now uses a real `src/samsarix_core` layout, retains a lightweight
  `helix_core` compatibility import, and has no unavailable sibling dependencies;
- the distribution and public product branding are now `samsarix-core` and
  Samsarix Core, maintained by Samsarix LLC;
- licensing is now the unmodified Mozilla Public License 2.0, with Samsarix LLC
  copyright, attribution, and trademark notices;
- the supported product is a local tool runtime, not the previously described
  orchestration, reasoning, UCF, or provider platform.
- structurally invalid but JSON-compatible outputs now report a declared-return-type
  mismatch rather than a generic JSON-compatibility message.
- missing-tool results no longer echo the caller-supplied unknown name.

### Removed from the supported surface

- the pre-2.0 prototype modules and their mock-only tests are archived under
  `legacy/` and excluded from built distributions.

### Release blockers

- owner selection of a publication destination and credentials for a future
  package-index release.
