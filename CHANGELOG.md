# Changelog

## 2.0.0a1 - Unreleased

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
