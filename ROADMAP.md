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
  cancellation, bounded progress notifications, and a message/admission-bounded
  concurrent stdio transport with an inventory example. Exact-head CI evidence
  remains required.
- Runtime input/output, batch, and registry resources are now capped and covered
  by adversarial tests.
- Timed-out sync work now retains its real concurrency slot and in-flight gauge;
  callers can inspect, wait for, and require bounded shutdown quiescence.
- Strict `TypedDict` input and output contracts now preserve named nested fields,
  descriptions, and required/optional key semantics in JSON Schema and runtime
  validation.
- External consumer: `samsarix-integration-examples` version 0.2.3 pins Core
  commit `beda0affe0dcc54c1a4e224bed26fbcd85e9184c` and proves a confined,
  privacy-first redaction workflow, exact typed result discovery, and
  response-free asynchronous cancellation through the public MCP API. It also
  proves progress-token correlation, monotonic content-free updates, notification
  ordering, cancellation cutoff, and artifact privacy.
- Next: exercise the contract from an independently operated desktop client and
  rerun the consumer matrix after GitHub Actions billing is restored. Use observed
  demand and confirmed contract gaps—not framework parity—to prioritize broader
  schema support.
- Review priority: Capture all 101 dirty/untracked paths.
- Review priority: split legacy relocation.
- Review priority: resolve license identity.
- Review priority: keep resource defaults aligned with adopter evidence.
- Review priority: validate shutdown deadlines with an external consumer.

## Release candidate

- Build and install the wheel in a clean environment.
- [x] Prove one real repository consumer and a versioned compatibility fixture.
- Publish only after package-name ownership, licensing, provenance, and rollback are recorded.

## Samsarix adoption

- Define a public API, event, schema, artifact, or deployment contract before connecting to Samsarix Unified.
- [x] Add a consumer-owned local-process contract fixture covering privacy,
  1 MiB source ingestion, safe errors, filesystem confinement, and version
  compatibility. Consumer-owned asynchronous MCP cancellation is now proven;
  bounded progress and cancellation cutoff are proven; synchronous timeout and
  bounded-quiescence evidence remains pending.
- Add authentication evidence only when an authenticated network transport is in
  scope; the supported stdio bridge delegates trust to the process launcher.
- Make one implementation canonical; remove or freeze duplicate behavior only after parity and rollback are proven.
- Record an owner, support level, compatibility window, and measurable adoption signal.

## Completion evidence

A milestone is complete only when its exact commit, commands and results, artifact digest, consumer or deployment, and rollback path are recorded in a pull request or release record. README claims must not exceed that evidence.
