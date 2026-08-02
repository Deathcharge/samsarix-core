# Security Policy

## Supported Versions

Only the current `2.0` alpha source line is under active security review. Code under
`legacy/` is an unsupported archive and is not shipped in the package.

## Reporting a Vulnerability

Use the repository's private GitHub Security Advisory interface when available.
Otherwise, email `support@samsarix.com` with the subject
`[Security] Samsarix Core vulnerability`.

Do not publish exploit details, secrets, or affected user data in a public issue.
Include the affected version or commit, realistic impact, prerequisites, a minimal
reproduction, and any proposed mitigation. Samsarix LLC does not currently promise
a particular response time or vulnerability bounty.

## System and Scope

Samsarix Core is a dependency-free, in-process Python library for declaring typed
local tools and invoking them through a bounded asynchronous runtime. Security
review covers `src/samsarix_core`, the `src/helix_core` compatibility import,
packaging configuration, and release artifacts produced from this repository.

The package does not provide a network service, accounts, authentication,
persistence, dynamic plugin loading, or an untrusted-code sandbox.

## Threat Model and Trust Boundaries

Invocation arguments may be controlled by an untrusted model or application
client. Registered callables and the host that selects them are trusted. Callables
run in the host process with its filesystem, environment, network, and credential
permissions.

The host remains responsible for authentication, authorization, tenant isolation,
quotas, transport controls, and deciding whether returned outputs or validation
details may be disclosed to a caller.

## Security Invariants

- Tool definitions reject ambiguous or unsupported contracts before registration.
- Invocation arguments are validated before execution; unexpected arguments are
  rejected and outputs are validated against the declared contract.
- Runtime concurrency and synchronous worker count remain bounded by configuration.
- Exception messages are redacted by default and runtime metrics retain no tool
  names, arguments, outputs, or exception content.
- Caller cancellation propagates, and a closed runtime rejects new invocations.
- The library does not claim to sandbox or authorize registered functions.

## Reportable Findings and Severity Context

A finding is reportable when it is realistically reachable in the supported
package under the documented trust boundary and violates an invariant or creates
confidentiality, integrity, or availability impact beyond documented behavior.

Examples include an attacker-controlled value bypassing validation in a materially
different shape, realistically bounded input defeating configured concurrency,
default error handling exposing secrets, or input data causing unintended code
execution independently of a deliberately registered callable.

Severity depends on attacker control, default reachability, reproducibility, and
concrete impact to the host process or its data.

## Out of Scope, Exclusions, and Accepted Risk

- Code under `legacy/` and unsupported versions.
- Vulnerabilities inside user-supplied callables or the host application's
  authentication, authorization, tenant, quota, transport, or logging layers.
- Disclosure caused solely by explicitly enabling `expose_exceptions=True`.
- Continued execution of an already-started synchronous callable after its result
  times out, unless a separate flaw defeats the documented concurrency or lifecycle
  bounds and materially amplifies the impact.
- Missing network admission, payload-size, or request-rate controls in a host
  application. Implementation-level resource exhaustion from realistically
  bounded input remains in scope.
- Automated scanner output without a reproducible supported-code impact.

## Known Limitations and Compensating Controls

Python cannot safely terminate a running worker thread. Synchronous tools must set
their own downstream I/O deadlines and make side effects safe when callers may
retry. Untrusted code requires a separate process or sandbox boundary.

The supported type-hint subset is deliberately narrower than Python's complete
typing language. Remote hosts must add their own request-size, rate, identity, and
authorization controls before invoking tools.
