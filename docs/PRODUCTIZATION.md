# Samsarix Core Productization Record

Last updated: 2026-08-31

## Current repository assessment

### Opt-in 2026 MCP ordinary-tool compatibility

The previous cancellation milestone merged in [PR #48](https://github.com/Deathcharge/samsarix-core/pull/48)
at `6da104f7923840f26686a742ed7036f27607d714`; all 18 exact-main CI jobs passed
in [run 33396263775](https://github.com/Deathcharge/samsarix-core/actions/runs/33396263775).
The next gap was modern clients having to fall back to legacy initialization.
Current primary-source research identified MCP `2026-07-28` as a substantial
protocol change, not just a version-number addition: stateless request metadata,
discovery, complete-result discriminators, cache hints and per-request logs are
required or relevant to Core's tool surface; task execution moved to a redesigned
extension. Sources and precise boundaries are in [the MCP guide](MCP.md#opt-in-mcp-2026-07-28).

Decision: provide `enable_modern=True` while leaving the default 2025 contract and
public result wrapping unchanged. Preserve ordinary tools and the existing runtime's
validation, host policy, concurrency/rate/circuit controls and cancellation. Do not
interpret the previous experimental tasks as the new extension or silently execute
unsupported continuation requests. This is a protocol adapter, not a new framework,
network service, SaaS frontend or reason to modify another repository.

- [x] Validate required metadata before execution and return supported-version errors.
- [x] Supply discovery, server identity, complete results, stable catalog order and
  conservative private zero-TTL cache hints without authentication assumptions.
- [x] Keep logging per-request, including concurrent calls; absent logLevel is silent.
- [x] Preserve legacy initialization when selected first; prevent cross-era state reuse.
- [x] Omit/reject legacy-task-required tools and reject task/MRTR call parameters.
- [x] Extend the real installed-wheel SDK 2.1.1 gate with modern discovery, ordinary
  calls, safe errors, progress, empty results and repeated cancellation/recovery.
- [x] Finish local regression, package and official-client verification; require
  exact-head CI before merge and record the hosted run evidence in the pull request.

The first real SDK 2.x modern and legacy runs passed against a locally built wheel.
A concurrent SDK 1.x run exposed an existing checker scheduling assumption. A
targeted repeat reproduced exact counters `active=0, cancelled=1, completed=0,
runtime_cancelled=0, runtime_timed_out=0, in_flight=1, pending=2`: the worker had
stopped and released execution capacity before the enclosing invocation finished
terminal accounting/admission cleanup. The gate now tolerates only this bounded
transient and still requires exact final counters within five seconds and at most
100 observations. Deterministic tests cover convergence and a permanently stuck
counter state; missing remote cancellation remains a failure. No runtime accounting
was changed to manufacture an atomic observation.

Final local verification: 379 tests passed with 95.41% branch-aware coverage,
including 29 modern protocol cases and 39 checker tests. Black checked 40 files;
Ruff, strict mypy (28 files), Bandit and `git diff --check` passed. An isolated
source-to-wheel build, strict Twine checks and the offline runtime/MCP/SQLite gate
passed. The final locally built wheel SHA-256 was
`646862ba77ac132bb8ac668fc9c418b70e77f5ac01e00aafec9f1903933449e1`.
All three official-client runs passed against that exact wheel: SDK 1.29.1 legacy,
SDK 2.1.1 legacy, and SDK 2.1.1 modern. Separately, the source-backed reproducer
passed 12 successive real SDK 1.x cancellation sessions (24 cancellations) after
the checker correction. This repeated diagnostic is distinct from wheel evidence.

Release disposition: unreleased opt-in API, not part of the immutable a9 wheel.
No new dependency or external service. The next release needs its own artifact and
provenance checks. HTTP/authentication, subscriptions, MRTR and redesigned tasks are
explicitly unsupported; signed-in desktop acceptance and separate-consumer upgrade
remain separate gates. Modern support does not claim broader schema adoption or
forced termination/rollback of arbitrary tool effects.

### Official-client cancellation and recovery

PR #47 merged at `84c305a9e98b4841ff3b231ebd4ab8bad01a3299`, with all 18
exact-main CI jobs passing in [run 33394265552](https://github.com/Deathcharge/samsarix-core/actions/runs/33394265552).
That established ordinary-call interoperability; it did not prove official-client
cancellation. Inspection of the pinned SDKs found an important host distinction:
1.29.1 abandons local waiting without notifying the server, whereas 2.1.1 sends a
courtesy cancellation notification. The checker now exercises both honest paths.

- [x] Add an in-memory fixture with one execution slot and public tool/runtime
  cleanup counters; wait for actual start progress rather than an arbitrary delay.
- [x] For 1.x, observe the exact ID in the SDK's typed outgoing request and send a
  typed cancellation notification before stopping the local waiter. No private SDK
  state or assumed progress-token/request-ID equality is used.
- [x] For 2.x, cancel only the local waiting task and require the SDK to send its
  notification. No injected cancellation can mask a broken automatic path.
- [x] Require two cancellation/recovery cycles with no active/completed waiters,
  exact cancellation counts, zero runtime timeouts and the same sole execution slot
  acquired by a follow-up tool. Bound start and recovery checks to five seconds.
- [x] Add negative controls for absent remote cancellation, leaked capacity,
  missing start, early completion, swallowed cancellation, timeout substitution and
  private progress; directly test the fixture and transparent request-ID observer.

Both real SDK versions passed against the unchanged published a9 wheel on
Windows/Python 3.11.9, SHA-256
`52ec76698f71584b29291e6b497ae94d8646721cafa38a49fed3ed7bf8e55e35`.
A real SDK 1.x negative control omitted only the explicit notification: after
observed start and local cancellation, the recovery call remained blocked and hit
its 0.5-second test bound. That expected failure confirms local cancellation alone
does not establish remote cleanup; it was not suppressed in the passing journey.
Local verification passed 340 tests with 95.23% branch-aware coverage, including
29 official-checker tests. Black checked 39 files, strict mypy checked 28 files,
Ruff and Bandit passed, and a fresh source-to-wheel build, strict Twine checks and
the existing offline runtime/MCP/SQLite gate passed. Hosted exact-head evidence
belongs to the pull request.
No Core runtime or public export change was needed; the existing six SDK CI jobs
now include this additional session. The independent server watchdog still bounds
failed cleanup. This is cooperative async cancellation evidence, not sync-thread
termination, durable rollback, task cancellation or signed-in user consent.
Reproduction uses the unchanged official-client command in [the MCP guide](MCP.md#official-python-client-verification).

### Official-client interoperability follow-up

After the a9 release, current upstream metadata identified official MCP Python SDK
`2.1.1` as released on 2026-08-25 and maintained `1.29.1` on 2026-08-24. Core's
description of `2025-11-25` as the current stable protocol was stale. This increment
keeps the supported revisions explicit instead of silently claiming newer features
or widening the runtime. The SDK's current `auto` client can negotiate backward;
that behavior needed actual external-client evidence, not just Core's own parser.

- [x] Add `scripts/verify_mcp_client.py` using official SDK transport, sessions and
  models; normalize v1/v2 Python naming through public wire aliases.
- [x] Run the server from an exact wheel in a fresh offline Core-only environment,
  outside the source checkout with isolated Python imports; reject SDK pin drift.
- [x] Verify discovery, schema validity, Unicode/newlines, output/text agreement,
  safe invalid-input results, synthetic private-input redaction, filtered logging,
  progress, empty results, error recovery and client-context shutdown.
- [x] Exercise SDK 2.x's default discovery-to-handshake fallback; assert the
  negotiated revision rather than treating current SDK support as modern MCP support.
- [x] Add independent client jobs for both SDK pins on Linux, Windows and macOS,
  leaving SDK dependencies out of Core's runtime and normal development install.
- [x] Bound session/checker/setup time, terminate a stuck checker and independently
  bound the server lifetime even when the SDK starts a separate process group;
  add checker negative controls for incorrect results, missing progress,
  private logs, version drift, ambiguous wheels, process failure and timeout cleanup.

Both pins passed on Windows/Python 3.11.9 against the actual downloaded a9 wheel,
SHA-256 `52ec76698f71584b29291e6b497ae94d8646721cafa38a49fed3ed7bf8e55e35`.
The initial checker run exposed a misspelled metadata-key assertion; that checker
defect was corrected before the passing runs. No Core runtime change was required.
SDK 2.x's expected logging deprecation warning remains visible because the journey
intentionally exercises a negotiated 2025 revision. The final full local suite passed
329 tests with 95.23% branch-aware coverage, including 18 checker regressions.
Black checked 38 files; Ruff, strict mypy (27 files) and Bandit passed. An isolated
source-to-wheel build, strict Twine checks and the existing offline runtime/MCP/SQLite
gate also passed. The SDK pins passed against the published artifact, not only a rebuild.
Final process-boundary review found that the SDK isolates its server's process group;
a stdlib-only 55-second server watchdog and normal-exit/forced-exit regression tests
were added before merge. A watchdog exit is a failed check, not a passing shutdown.
Hosted exact-head matrix/build evidence is recorded in the pull request; this is
not a claim that the separate repository consumer has upgraded.

At that milestone, the client checks did not cover tasks, cancellation, desktop-client trust,
HTTP/authentication or newer protocol features. Task APIs removed upstream in SDK
2.x are not silently emulated or advertised as compatible. Newer protocol semantics
and official-client cancellation were next priorities, separately from that verified
backward-compatible journey. The SDK pins are exact but their transitive dependencies
resolve at installation time. No production service, credentials, telemetry or
external tool invocation is added. Reproduction commands and primary upstream
references are in [the MCP guide](MCP.md#official-python-client-verification).

### 2.0.0a9 verified distribution

The boundary fixes merged in [PR #44](https://github.com/Deathcharge/samsarix-core/pull/44)
at `bc1fe2b2a6c9a215b37a698056c633795072fbd0`. CodeRabbit completed a full review
of `c4712d80bae085789ad4fadb2f74272f7e16f60f`; its sole actionable checksum-glob
comment was fixed in `5198a8abae98cc98df170480cf8640c4eb9440dc` and the thread
resolved. That follow-up added an explicit `--` option terminator and a regression
assertion; it was not represented as a second full review. All 12 exact-main CI
jobs passed in [run 33390409997](https://github.com/Deathcharge/samsarix-core/actions/runs/33390409997).

Release preparation [PR #45](https://github.com/Deathcharge/samsarix-core/pull/45)
merged at `8957b208db4ee08a32e9c66cf0cf50b7dc7422a4`. All 12 exact-main CI jobs
and the build-only dry run passed before the annotated `v2.0.0a9` tag was pushed.
The immutable GitHub prerelease was published on 2026-08-31. A subsequent manual
dispatch on the actual tag also passed with attestation and publication skipped,
proving the new event guard in addition to its source-level regression test.

All three fresh release downloads passed immutable membership and digest checks.
Wheel and source-distribution provenance passed exact repository, workflow, tag
and source-commit constraints with self-hosted runners denied. One wheel verifier
initialization failure resolved on an identical retry; no constraint was relaxed.
The downloaded wheel installed offline into a fresh Python 3.11.9 environment and
passed the expanded runtime, bounded diagnostic/numeric, real MCP subprocess and
SQLite transaction/replay gate. The source suite passed 311 tests with 95.23%
branch-aware coverage. See [release evidence](RELEASING.md#published-evidence-v200a9)
for asset digests, hosted runs and exact verification commands.

Disposition: a useful, reproducible evaluation alpha, not a stable API or proven
third-party production offering. This increment adds no public exports, runtime
dependencies, services, telemetry or retries. No PyPI upload, deployment, paid
account, user data or other-repository change was needed. Next: upgrade and rerun
the separate consumer at the new exact release, complete operator-owned client
trust/tool approval, and collect real workload feedback before expanding scope.

### Post-a8 input-boundary review and remediation

An offline standard security review at clean `ced7be6ee96ba08af5ecb92bfc2683ee6466ab9b`
covered all 69 supported tracked files; the 38 unsupported `legacy/` files were
explicitly excluded. Independent baseline, architecture, and focused boundary
reviews were reconciled against source. The generated local report is scan
`3565ffc8-e944-47f3-afaa-859cdc36624a`. No application code or network access was used
during that scan, and the advisory connector was unavailable. The report describes
the pre-fix commit, not the patched tree.

The review confirmed medium-severity diagnostic amplification before execution and
low-severity numeric overflow affecting a host-owned mixed batch. It also confirmed
session-local MCP malformed-method/Unicode failures and output-frame overflow as
reliability defects, without claiming a built-in remote service or new client authority.

- [x] Bound error aggregation at every nesting level to 64 issues including an
  explicit truncation marker; cap paths/messages at 128 characters and abbreviate
  dictionary keys before composing descendant paths. Preserve valid long-key data,
  short diagnostics, and valid alternatives after failed union validation.
- [x] Normalize float overflow into finite-number validation errors, including
  nested annotations, float-first unions, defaults, outputs, and ordered batches.
- [x] Guard MCP method classification, escape lone-surrogate metadata safely,
  and bound final fallback frames including their newline and oversized IDs.
- [x] Add installed-wheel numeric/diagnostic and real-pipe malformed-MCP checks,
  including negative controls for defective package checkers.
- [x] Require an actual tag-push event for privileged release steps; preserve manual
  dispatch as build-only even on a tag ref. Include that workflow in source archives
  so its source-level regression test has the required fixture.
- [x] Clarify lazy experimental task cleanup: TTL limits access, not timed physical
  memory erasure. Remove the stale version-specific API introduction.

Before fixes, the new suites reproduced 14 validation failures and 11 MCP failures
on bounded payloads (the two initialization fixtures were corrected and independently
reproduced their UTF-8 failures). No full-scale memory-exhaustion payload was run.
After fixes, `python -m pytest` passed 311 tests with 95.23% branch-aware coverage;
Black checked 35 files, Ruff passed, strict mypy checked 25 files, and Bandit over
`src` passed. The fixes add no public exports, dependencies, external services,
telemetry, or automatic retries. An isolated source-distribution-to-wheel build and
strict Twine checks passed, followed by a fresh offline install exercising runtime
boundaries, real MCP pipes, and SQLite transaction/replay. The actual published a8
wheel matched its known SHA-256 but failed the expanded checker with the expected
numeric `OverflowError`; that is a negative control, not a new passing a8 claim.
Hosted exact-commit and new-release evidence is recorded above. Published
a8 remains immutable and does not acquire these fixes retroactively.

### 2.0.0a8 verified distribution

The finite-deadline fix merged in [PR #41](https://github.com/Deathcharge/samsarix-core/pull/41)
at `1c05fb4bd46d4836b2f4ced6698d3071d7b00eeb`; all 12 exact-main CI jobs passed in
[run 33385148670](https://github.com/Deathcharge/samsarix-core/actions/runs/33385148670).
CodeRabbit completed its full review with no actionable findings (a non-blocking
test/helper docstring-coverage warning remains separate from required quality gates).
A freshly downloaded a7 wheel matched its immutable release and known digest, but
correctly failed the new gate with `invalid deadline was not rejected`.

Release preparation [PR #42](https://github.com/Deathcharge/samsarix-core/pull/42)
synchronized the package/citation metadata and dated the changelog. All 12 exact-main
CI jobs and the build-only release dry run passed before the annotated `v2.0.0a8`
tag was pushed at `dfaf41ee850ff94c7f106c60a6752865fb364ad4`. The immutable GitHub
prerelease was published on 2026-08-31, with unchanged historical a7 assets.

Fresh downloads passed release membership and SHA-256 manifest verification. Both
distribution attestations passed explicit repository, workflow, source-ref and source
digest constraints with self-hosted runners denied. The downloaded wheel installed
offline into a fresh Python 3.11.9 environment and passed runtime/deadline, ordered
batch, circuit recovery, MCP subprocess and SQLite transaction/replay checks.
See `docs/RELEASING.md` for exact assets, digests, workflow IDs and verification commands.

Disposition: a reproducible, useful evaluation alpha for typed Python tools, not a
stable API or independently proven production service. No PyPI upload, deployment,
paid account, new dependency, external data or other-repository change was needed.
At that release, the next priority was a consumer-owned a8 upgrade and workload feedback;
the existing exact-pin consumer evidence is not silently extended to this release.

### Finite-deadline validation follow-up

At clean main `0ccd94b55f0ade481ce073bf3e495f8b1711c73f`, a bounded reproduction
found that NaN and infinity were accepted as execution deadlines, while an integer
such as `10**1000` could leak `OverflowError` and abort an entire batch. Invalid
wait/close timeouts were also accepted, and overflowing MCP task TTLs produced an
internal-server error rather than invalid parameters. These were real validation
defects affecting otherwise valid calls, not a need for a broader scheduling API.

- [x] Normalize finite durations before decorator metadata, runtime construction,
  invocation admission, and shutdown side effects.
- [x] Preserve timeout precedence, positive finite values, explicit `None` semantics,
  and zero-duration sync polling; reject bad overrides with `invalid_timeout`.
- [x] Prove invalid calls do not reach policy or execution, consume capacity/rate
  tokens, trip circuits, leak inputs, or abort good batch items.
- [x] Reject unrepresentable task-duration configuration and requested TTLs; prove
  invalid parameters leave the sole task slot and protocol request ID reusable.
- [x] Add installed-wheel deadline/batch regression checks and prove the checker
  catches discarded deadlines and dropped batch items.

Local verification passed: `python -m pytest` (279 tests, 94.87% branch-aware coverage),
Black (33 files), Ruff, strict mypy (25 files), and Bandit over `src`. The 39 new cases
include 37 runtime/protocol regressions and two negative controls for the package
checker. An isolated sdist-to-wheel build, strict Twine check and fresh offline wheel
installation passed, including actual deadline/batch behavior, MCP subprocess pipes,
and SQLite transaction/replay. Hosted exact-head evidence belongs to the pull request.

This intentionally tightens invalid configuration handling without new public exports,
dependencies, services or telemetry. Finite does not mean operationally sensible: the
host must still choose practical deadlines. Async cancellation cleanup is cooperative,
sync workers cannot be force-killed, and `aclose(timeout=...)` bounds its sync-worker
wait rather than all async cancellation. Docs now distinguish these limitations.
The immutable published a7 wheel does not include this fix and cannot pass the newly
expanded deadline gate; its earlier verification remains historical evidence. The fix
is now distributed in the separately verified a8 release described above.

### Transactional application example follow-up

At clean main `048f26a608201d8a09a8d826f041f6598baaa0ee`, 208 tests passed with
94.81% branch-aware coverage on Windows/Python 3.11.9. The docs advised making side
effects idempotent, but the reservation examples only returned shaped responses.
The next adoption gap was a real, reproducible write/replay journey, not a generic
runtime persistence or retry layer.

- [x] Add an application-owned SQLite inventory store and typed sync tools.
- [x] Commit stock and its bounded request ledger atomically; replay identical keys,
  reject conflicting key reuse, and preserve terminal business rejections.
- [x] Prove concurrent duplicate/competing requests across runtime instances,
  statement/commit rollback, finite lock waiting and replay in a separate process.
- [x] Commit real data before deliberately withholding a sync response; prove that
  timeout/cancellation retains the worker, quiescence is observable, and a later replay
  never decrements stock again.
- [x] Run the self-verifying demo with the isolated installed-wheel gate; keep the
  earlier MCP preview read-only and clarify the policy-only example's simulation.

`docs/SIDE_EFFECTS.md` specifies business outcomes separately from runtime status,
host-owned authorization and database paths, single-tenant request identity, finite
retention without automatic eviction, explicit connections and transaction boundaries,
and unproven production properties. SQLite storage is confined to this example, not
added to Core's API or runtime requirements. No external account, production data,
service, network call or paid dependency is needed.

Local final verification passed: 240 tests with 94.81% branch-aware Core coverage,
Black (31 files), Ruff, strict mypy (24 files), and Bandit over Core plus the new
SQLite example. The isolated sdist-to-wheel build and strict Twine checks passed;
the fresh offline installed-wheel gate passed exports/runtime behavior, real MCP
pipes, and the SQLite commit/replay demonstration. The policy preview was also run
and produced the expected denial followed by an allowed preview. The 32 new example
tests are behavioral evidence, not a claim of power-loss or third-party deployment
validation. Exact-head hosted checks are recorded in the corresponding pull request.

### Dependency-outage evaluation follow-up

At clean main `6ded14d4a5a1a1754d5d080a8dad763161c19b3d`, 185 tests passed with
94.73% branch-aware coverage on Windows/Python 3.11.9. The existing no-I/O
microbenchmarks did not quantify interference from a failing dependency or the cost
trade-off of limiting that dependency's concurrency. This was an evaluation-evidence
gap, not a newly discovered runtime defect or a reason to expand the public API.

- [x] Add a bounded synthetic mixed-vendor/cache workload using the real public API.
- [x] Compare global capacity, a per-vendor bulkhead, and bulkhead plus circuit control
  with the same finite request burst and an event-based saturation barrier.
- [x] Verify exact successful cache outputs, real vendor executions, safe failures,
  capacity/metrics, cancellation cleanup, and missing-control detection.
- [x] Preserve every repeated measurement and the benchmark digest; document both
  faster unrelated requests and the slower failure-drain trade-off of a bulkhead.

The recorded five-repetition run made 64 vendor requests and 32 cache requests per
scenario. All cache calls succeeded; circuit control reduced actual vendor executions
from 64 to two, returning 62 safe failures rather than useful work. See
`docs/BENCHMARKS.md` and its raw report for timings, methodology and limitations.
This improves independent evaluation for tool-runtime adopters but is synthetic local
evidence, not third-party production adoption. No runtime source, dependency, hosting,
telemetry, published artifact or public API was changed.

Final local checks passed: `python -m pytest` (208 tests, 94.81% branch-aware coverage),
`python -m black --check src tests examples benchmarks scripts` (29 files),
`python -m ruff check src tests examples benchmarks scripts`, `python -m mypy`
(23 files), and `python -m bandit -q -r src`. An isolated `python -m build`, strict
Twine check, and `scripts/verify_distribution.py` passed for the candidate wheel.
An additional one-repetition run at 512 vendor calls, 512 cache calls and 1 ms delay
passed all three scenarios with zero admission rejections, correct cache results and
510 circuit rejections after two actual vendor executions in the guarded scenario.
Hosted exact-head verification is recorded in the pull request.

### Current verification follow-up

At clean main `4f5d04d3cf3c1f7b2dcec693154d502dd0f6f1b2`, the baseline suite passed
177 tests with 94.73% branch coverage on Windows/Python 3.11.9. Two release-evidence
gaps remained despite the green source suite: the shared wheel smoke only checked
exports/model construction, and hosted package verification ran only on Linux.
The previously claimed automated circuit-recovery smoke was therefore overstated.

- [x] Replace the import-only gate with real installed sync/async, validation, batch,
  redacted circuit failure/recovery, metrics and quiescence checks.
- [x] Exercise the documented inventory MCP server through actual subprocess pipes,
  including UTF-8, operational logging, progress ordering, and EOF shutdown.
- [x] Prove checker failures for wrong output/version, malformed stdout, ambiguous
  artifacts, and a hung child; retain checks under Python optimization.
- [x] Add fresh offline-wheel CI at Python 3.10 and 3.14 on Linux, Windows, and macOS.
- [x] Re-download and verify the unchanged a7 wheel with the expanded gate locally;
  keep artifact publication and new verification-script provenance distinct.

These changes strengthen reproducible package evaluation for Python tool developers.
They add no runtime dependencies, API surface, telemetry, hosting, or external service.
See `docs/RELEASING.md` for commands and the explicit historical evidence correction.
Local final verification: 185 tests passed with 94.73% branch-aware coverage; Black,
Ruff, strict mypy (22 files), source Bandit, isolated build and strict Twine checks
passed. Both the new candidate and freshly downloaded immutable a7 wheel passed the
offline installed-package gate on Windows/Python 3.11.9. Hosted results are recorded
on the corresponding pull request rather than inferred from this local execution.

### Original assessment

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
- Offer an optional host-owned pre-execution policy after validation. Current MCP
  guidance recommends a human denial surface, while current OpenAI Agents SDK and
  LangChain documentation expose per-tool guardrails or conditional approval policies:
  <https://modelcontextprotocol.io/specification/2025-11-25/server/tools>,
  <https://openai.github.io/openai-agents-python/guardrails/>, and
  <https://docs.langchain.com/oss/python/langchain/human-in-the-loop>. Core supplies
  only a bounded programmatic allow/deny boundary; client UI and durable approval state
  remain outside this runtime.
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
- [x] Add opt-in per-tool sustained-rate controls with bounded burst, safe retry
  metadata, and consistent direct, batch, MCP, and task semantics.
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
- Added opt-in experimental MCP task augmentation for long-running local jobs, with
  per-tool negotiation, secure IDs, finite in-memory retention, polling, blocking
  result retrieval, cancellation, and conservative omission of unauthenticated
  task listing.
- Added stable MCP progress notifications with invocation-scoped async reporting,
  strict monotonicity, update and UTF-8 message caps, cancellation cutoff, and
  custom-transport failure propagation.
- Added registry, batch, value-complexity, argument, and output resource budgets,
  plus observable bounded shutdown quiescence for timed-out synchronous work.
- Added an async invocation policy with detached validated context, explicit decisions,
  bounded evaluation, timeout/cancellation integration, safe denial/failure results,
  and content-free denial metrics across direct, batch, MCP, and MCP task execution.
- Added host-configured per-tool execution bulkheads that acquire before global runtime
  capacity, preserve unrelated tool availability, and retain their slot for surviving
  synchronous work after timeout or cancellation.
- Added host-configured per-tool token buckets immediately before execution, with
  sustained refill and burst controls, safe retry delays, policy-aware accounting,
  content-free metrics/lifecycle, and ordinary/task MCP serialization.
- Added provider-neutral lifecycle observability with immutable content-free event
  models, paired logical start/terminal signals, cancellation and host-abort coverage,
  non-interfering handler failure accounting, and documented OpenTelemetry mapping.
- Proved the public MCP API, exact typed result discovery, response-free
  asynchronous cancellation, bounded content-free progress, and client-filtered
  operational logging, retained sync-worker capacity after timeout, and bounded
  shutdown quiescence, official MCP Inspector invocation, and Visual Studio Code
  configuration discovery from `samsarix-integration-examples`; version 0.2.12 at merge
  commit `be56db8476454d6f241a5da7d5e846d92d1bcefb` pins Core commit
  `2744d69eb58aef8412d15fbee9485b6d22eb30a5` and additionally proves the bounded
  experimental task lifecycle, allow/deny invocation policy, fail-fast runtime
  admission, paired content-free lifecycle observation, and process-local per-tool
  rate limiting and per-tool circuit failure, fail-fast rejection, and successful
  half-open recovery on the real redaction adapter.

## Deferred work and rationale

P2 framework/provider adapters, durable registry/invocation persistence, process
isolation, and richer schema types remain deliberately deferred. Experimental MCP
tasks retain bounded results only inside one server process and do not satisfy durable
persistence or restart recovery. Those features are not required for the first useful
release. One independent repository now proves the stable MCP boundary, experimental
task lifecycle, bounded policy gate, fail-fast runtime admission, and privacy-safe
lifecycle observation. Core now also supplies the process-local per-tool rate and
circuit controls required by its supported MCP tool boundary. Subsequent surface
area should follow concrete consumer demand. Core's per-tool rate-limit pull request
[Python 3.10-3.14 hosted matrix](https://github.com/Deathcharge/samsarix-core/actions/runs/31241493059)
is green. The consumer's separate Python 3.11-3.13 jobs could not start because GitHub
reported an account billing/spending-limit problem, so its local 38-test exact-pin and
clean-wheel behavioral evidence is recorded separately in `docs/ADOPTION.md`.

## Owner-, credential-, or production-blocked tasks

The immutable GitHub prerelease `v2.0.0a8` is published from commit
`dfaf41ee850ff94c7f106c60a6752865fb364ad4` with verified checksums, GitHub Actions
build provenance, and clean installed-wheel runtime, MCP and SQLite checks. The exact assets,
workflow runs, verification, installation evidence, and recovery model are recorded in
`docs/RELEASING.md`. This passes the GitHub release gate only; it does not pass the
PyPI, stable API, or third-party production-adoption gates.

- Decide whether commercial licensing, paid support, or a service-level agreement
  will be offered separately from the MPL-2.0 community distribution. None is
  promised by this repository.
- PyPI publication, account creation, and service deployment remain separate owner
  decisions. The owner has authorized this repository's verified GitHub prerelease.

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
- The MCP stdio adapter and runtime have per-message and per-invocation byte limits plus
  opt-in process-local per-tool rate controls, but no authenticated tenant quota,
  cross-process rate coordination, connection limit, or aggregate-memory limit. Any
  remote host must apply those controls before invocation.
- Public package-index publication still requires owner-controlled credentials and
  an explicit release decision.
- Experimental task results are retained in process until a finite TTL. Task IDs are
  secure random values and stdio does not expose listing, but possession grants
  get/result/cancel access within that logical session; a network host must bind task
  operations to authenticated requestor identity.

## Distribution and sustainability model

The simplest distribution is a pure-Python wheel and source distribution built
from GitHub tags, with no hosted service and no required API account. Operating
cost is therefore zero for the library itself; adopters pay only for infrastructure
or providers they choose outside Samsarix Core.

The unmodified MPL-2.0 license protects distributed changes to covered files while
allowing use in larger proprietary applications. Sustainability can come from paid
integration, support, hosted products, or separate commercial arrangements, but
none of those offerings or any revenue and demand claims are assumed here.
