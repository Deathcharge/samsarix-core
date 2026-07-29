# Best practices

## Keep tools small and explicit

Use one action per function, narrow annotations, short docstrings, and stable names.
Prefer JSON-native return values over custom objects. Use `version` as application
metadata when a contract changes; Samsarix Core does not route versions for you.

## Treat calls as untrusted input

Type validation does not replace authorization. Re-check tenant, user, path,
resource, and quota permissions inside the tool. Prefer allowlists and resolved
resource IDs over raw filesystem paths or shell fragments.

Never register a callable merely because an untrusted client supplied its import
path. The registry is for trusted application code, not dynamic code loading.

## Protect sensitive data

Leave `expose_exceptions=False` in shared environments. Do not place credentials in
tool descriptions, tags, defaults, arguments sent to a model, outputs returned to
an untrusted caller, or external logs.

Samsarix Core itself does not log call content. If the host adds logging or tracing,
record status, duration, and an application-approved tool identifier; redact inputs,
outputs, exception messages, and authorization material by default.

## Bound every external dependency

The runtime timeout bounds how long the caller waits. A sync function's thread
cannot be force-stopped. Set connect/read/query/process timeouts in the tool itself,
make cancellation-friendly async calls, and make side effects idempotent when the
caller might retry after a timeout.

Choose `max_concurrency` from downstream capacity, not CPU count alone. Apply
application-level admission control before accepting an unbounded number of calls.

## Handle results deliberately

Branch on `ToolStatus`; do not infer success from a truthy output. The runtime does
not mark any failure retryable because a timed-out sync function may still finish
and cause its side effect. Apply a retry policy only when the tool's semantics make
that safe.

Let caller cancellation propagate. Use `async with ToolRuntime(...)` so resources
close on success and failure.

## Test contracts, not mocks

Test schema output, missing/extra/wrongly typed arguments, successful sync and async
calls, output validation, failure redaction, timeout behavior, cancellation, and
concurrency limits. Install the built wheel in an isolated environment before a
release; importing from the source checkout alone does not validate packaging.
