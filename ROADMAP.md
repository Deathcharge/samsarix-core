# Samsarix Core roadmap

This roadmap separates four gates: merge, release, publication, and flagship adoption. Passing one does not imply the next.

## Product boundary

Portfolio role: **reusable library or sdk**. Keep this as a small, independently versioned package. Samsarix Unified should consume it only through a public API adapter; private monorepo imports and copied implementations are out of scope.

Current disposition: The productized runtime, MCP bridge, resource bounds, and
sync-quiescence work are merged. An independent repository now provides exact-pin
compatibility evidence; release, publication, and third-party production adoption
remain separate decisions.

## Stabilize the productized default

- Keep the default branch buildable from a clean checkout and preserve exact-head CI evidence.
- Keep Samsarix LLC branding, package identity, license metadata, and compatibility aliases internally consistent.
- Preserve the pre-productization default under a rollback ref before merging; do not delete legacy history.
- The productization work is now committed, pushed, clean, and green in hosted checks.
- MCP flagship adapter: implemented lifecycle negotiation, JSON Schema tool discovery,
  structured invocation results, behavioral safety hints, active-call
  cancellation, bounded progress notifications, opt-in content-free operational
  logging, opt-in experimental task-augmented execution with finite in-memory
  retention, and a message/admission-bounded concurrent stdio transport with an
  inventory example. Exact-head CI evidence remains required.
- Runtime input/output, batch, and registry resources are now capped and covered
  by adversarial tests.
- A host-owned async policy can centrally allow or deny validated direct, batch, MCP,
  and task calls before execution; evaluation is bounded and fails closed without
  replacing client authentication or durable human approval.
- Timed-out sync work now retains its real concurrency slot and in-flight gauge;
  callers can inspect, wait for, and require bounded shutdown quiescence.
- Tool registrations can apply deployment-local concurrency bulkheads before the
  global execution semaphore, preventing one slow or quota-constrained dependency
  from starving unrelated tools across direct, batch, MCP, and task invocation.
- Tool registrations can also apply process-local token buckets immediately before
  execution, protecting sustained downstream request quotas with safe retry hints
  without treating the runtime as a distributed or per-tenant quota service.
- Tool registrations can opt into process-local consecutive-failure circuit breakers
  that fail fast before capacity and rate tokens, invalidate queued stale permits,
  allow one half-open recovery probe, and expose safe results plus host inspection/reset
  without automatic retry or distributed-health claims.
- Strict `TypedDict` input and output contracts now preserve named nested fields,
  descriptions, and required/optional key semantics in JSON Schema and runtime
  validation.
- External consumer: `samsarix-integration-examples` version 0.2.12 pins Core
  commit `2744d69eb58aef8412d15fbee9485b6d22eb30a5` and proves a confined,
  privacy-first redaction workflow, exact typed result discovery, and
  response-free asynchronous cancellation through the public MCP API. It also
  proves progress-token correlation, monotonic content-free updates, notification
  ordering, cancellation cutoff, artifact privacy, client-selected operational-log
  filtering, content-free terminal events, retained sync-worker capacity after timeout,
  and bounded shutdown quiescence. Its portable Visual Studio Code workspace is
  configuration-discovered by VS Code 1.131.0; the preceding v0.2.6 contract was also
  independently discovered and invoked through official MCP Inspector 0.21.2. The
  consumer now proves real redaction through task creation, status, blocking result
  retrieval, related-task progress, bounded private retention, and safe task cancellation.
  It also proves the host-policy allow path and safe pre-execution denial of an
  independently registered out-of-contract tool without private-input disclosure.
  Runtime saturation additionally proves fail-fast retryable overload signaling,
  policy bypass, private-argument redaction, and capacity cleanup after cancellation.
  A host-owned Core lifecycle handler also proves paired, correlated start/success
  events without secrets, filenames, run IDs, output names, or workspace paths.
  It now also proves a policy-gated real redaction succeeds under an opt-in per-tool
  token bucket while an immediate second call is safely rate limited without execution,
  a second artifact, private-input retention, or incorrect aggregate metrics.
  It now also proves that a host-owned per-tool circuit opens after a private downstream
  failure, rejects the next request without execution or an artifact, and closes after
  one successful real redaction recovery probe without leaking private protocol content.
- Next: upgrade the private same-owner consumer to the verified a10 release, rerun its own CI
  matrix, and complete the signed-in Visual Studio Code trust/tool-approval journey. Use observed
  demand and confirmed contract gaps—not framework parity—to prioritize broader
  schema support.
- Initial worktree capture, legacy relocation, and Samsarix LLC/MPL-2.0 identity
  reconciliation are complete; preserve their history and compatibility boundary.
- Review priority: keep resource defaults aligned with adopter evidence.
- Review priority: complete signed-in Visual Studio Code trust and invocation acceptance.

## Release candidate

- [x] Prove a real transactional write journey with bounded application-owned
  idempotency records, concurrent replay, rollback, and recovery after a lost response.
- [x] Provide a reproducible mixed-dependency outage evaluation with actual execution
  counts, unrelated-tool latency, isolation trade-offs, and bounded cleanup checks.
- [x] Verify installed wheel runtime behavior and the documented MCP example through
  real subprocess pipes, with offline isolated installs and bounded checker cleanup.
- [x] Add Linux, Windows and macOS package verification at Python 3.10 and 3.14.
- [x] Add an independent official MCP client gate for maintained SDK 1.x and
  current SDK 2.x against isolated installed wheels on Linux, Windows and macOS.
- [x] Prove cooperative cancellation and sole-slot recovery through both pinned
  official clients, keeping explicit 1.x and automatic 2.x notification paths distinct.
- [x] Evaluate MCP `2026-07-28` and add an opt-in ordinary-tool stdio path, preserving
  default 2025 contracts and proving modern discovery separately from client fallback.
- [x] Release the opt-in modern path after exact-head verification; keep task
  extensions, multi-round-trip operations and network transport separate decisions.
- [x] Provide a public MCP workflow over the existing SQLite reservation store, with
  host-gated writes, real process-restart replay, independent disk assertions and
  no dependency on the private consumer. Keep candidate qualification distinct from adoption.

- [x] Build and install the wheel in a clean environment.
- [x] Prove one real repository consumer and a versioned compatibility fixture.
- [x] Publish immutable GitHub prerelease `v2.0.0a1` after package identity, licensing,
  provenance, verification, and rollback are recorded. PyPI remains a separate gate.
- [x] Publish immutable GitHub prerelease `v2.0.0a4` with per-tool bulkhead,
  concurrent-registration, mixed-batch fairness, clean-install, checksum, and SLSA
  provenance evidence.
- [x] Publish immutable GitHub prerelease `v2.0.0a5` with privacy-safe lifecycle
  observability, independent consumer, clean-install, checksum, and SLSA provenance
  evidence.
- [x] Publish immutable GitHub prerelease `v2.0.0a6` with per-tool rate limiting,
  independent consumer, clean-install, checksum, and SLSA provenance evidence.
- [x] Prove independent consumer adoption for the per-tool circuit-breaker contract
  after exact-head review and clean-wheel evidence.
- [x] Publish immutable GitHub prerelease `v2.0.0a7` with per-tool circuit breaking,
  independent consumer, clean-install, checksum, and SLSA provenance evidence.
- [x] Publish immutable GitHub prerelease `v2.0.0a8` with finite-deadline rejection,
  SQLite write/replay and dependency-outage evidence, and real installed-wheel gates.
  This does not extend the older consumer pin's evidence to the new release.
- [x] Publish immutable GitHub prerelease `v2.0.0a9` with bounded derived diagnostics,
  float-overflow isolation, malformed-MCP frame handling, exact-source provenance,
  and fresh installed-wheel checks. Prove manual dispatch on the tag remains
  build-only. The separate consumer still needs its own upgrade and verification.
- [x] Publish immutable GitHub prerelease `v2.0.0a10` with opt-in MCP `2026-07-28`
  ordinary tools, exact-source provenance and fresh downloaded-wheel verification
  using both official SDK pins, legacy negotiation and modern discovery, including
  repeated cooperative cancellation/recovery. Retain the same adoption boundaries.

## Samsarix adoption

- Define a public API, event, schema, artifact, or deployment contract before connecting to Samsarix Unified.
- [x] Add a consumer-owned local-process contract fixture covering privacy,
  1 MiB source ingestion, safe errors, filesystem confinement, and version
  compatibility. Consumer-owned asynchronous MCP cancellation, bounded progress,
  cancellation cutoff, content-free operational logging, synchronous timeout
  accounting, bounded shutdown quiescence, and the experimental MCP task lifecycle are
  now proven.
- Add authentication evidence only when an authenticated network transport is in
  scope; the supported stdio bridge delegates trust to the process launcher.
- Make one implementation canonical; remove or freeze duplicate behavior only after parity and rollback are proven.
- Record an owner, support level, compatibility window, and measurable adoption signal.

## Completion evidence

A milestone is complete only when its exact commit, commands and results, artifact digest, consumer or deployment, and rollback path are recorded in a pull request or release record. README claims must not exceed that evidence.
