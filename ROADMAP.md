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
- Strict `TypedDict` input and output contracts now preserve named nested fields,
  descriptions, and required/optional key semantics in JSON Schema and runtime
  validation.
- External consumer: `samsarix-integration-examples` version 0.2.10 pins Core
  commit `e20a4e982b24dbc7ff2b5c78714742bfd1ee2f90` and proves a confined,
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
- Next: complete the signed-in Visual Studio Code trust/tool-approval journey and rerun
  the consumer matrix after GitHub Actions billing is restored. Use observed
  demand and confirmed contract gaps—not framework parity—to prioritize broader
  schema support.
- Review priority: Capture all 101 dirty/untracked paths.
- Review priority: split legacy relocation.
- Review priority: resolve license identity.
- Review priority: keep resource defaults aligned with adopter evidence.
- Review priority: complete signed-in Visual Studio Code trust and invocation acceptance.

## Release candidate

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
