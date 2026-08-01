# Samsarix Core roadmap

This roadmap separates four gates: merge, release, publication, and flagship adoption. Passing one does not imply the next.

## Product boundary

Portfolio role: **reusable library or sdk**. Keep this as a small, independently versioned package. Samsarix Unified should consume it only through a public API adapter; private monorepo imports and copied implementations are out of scope.

Current disposition: Merge the productization branch after exact-head verification and rollback-ref creation; release and adoption remain separate decisions.

## Stabilize the productized default

- Keep the default branch buildable from a clean checkout and preserve exact-head CI evidence.
- Keep Samsarix LLC branding, package identity, license metadata, and compatibility aliases internally consistent.
- Preserve the pre-productization default under a rollback ref before merging; do not delete legacy history.
- The productization work is now committed, pushed, clean, and green in hosted checks.
- MCP flagship adapter: implemented lifecycle negotiation, JSON Schema tool discovery,
  structured invocation results, behavioral safety hints, and a bounded stdio
  transport with an inventory example. Exact-head CI evidence remains required.
- Runtime input/output, batch, and registry resources are now capped and covered
  by adversarial tests.
- Timed-out sync work now retains its real concurrency slot and in-flight gauge;
  callers can inspect, wait for, and require bounded shutdown quiescence.
- Next: prove adoption from one external consumer, then prioritize richer nested
  schema types from that integration evidence.
- Review priority: Capture all 101 dirty/untracked paths.
- Review priority: split legacy relocation.
- Review priority: resolve license identity.
- Review priority: keep resource defaults aligned with adopter evidence.
- Review priority: validate shutdown deadlines with an external consumer.

## Release candidate

- Build and install the wheel in a clean environment.
- Prove one real consumer and a versioned compatibility fixture.
- Publish only after package-name ownership, licensing, provenance, and rollback are recorded.

## Samsarix adoption

- Define a public API, event, schema, artifact, or deployment contract before connecting to Samsarix Unified.
- Add a consumer-owned contract fixture covering authentication, privacy, limits, errors, and version compatibility.
- Make one implementation canonical; remove or freeze duplicate behavior only after parity and rollback are proven.
- Record an owner, support level, compatibility window, and measurable adoption signal.

## Completion evidence

A milestone is complete only when its exact commit, commands and results, artifact digest, consumer or deployment, and rollback path are recorded in a pull request or release record. README claims must not exceed that evidence.
