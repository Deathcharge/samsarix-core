# Adoption evidence

This record separates package compatibility evidence from production-adoption
claims. Samsarix Core has a merged independent repository consumer; it does not
yet have a documented third-party production deployment, paid customer, usage
volume, or service-level commitment.

"Independent repository" means a separately packaged codebase, not an independently
operated company or customer. GitHub's API confirmed on 2026-08-31 that the consumer
repository is private and the Guard/Orchestration dependencies are public. The owner
can inspect the linked consumer evidence; public readers cannot reproduce it without
access. Core never requires this private repository to install or run. Use the public
[SQLite/MCP reservation example](SIDE_EFFECTS.md#use-the-persistent-store-from-an-mcp-client)
for a credential-free stateful workflow.

The latest published `2.0.0a11` prerelease has verified immutable artifacts, provenance,
and installed-wheel runtime/deadline, bounded diagnostic/numeric, malformed-MCP
subprocess and SQLite transaction/replay behavior, plus official-client legacy and
opt-in modern MCP ordinary-tool/cancellation journeys against the downloaded wheel.
It also packages the public persistent SQLite MCP launcher and official-client
write/restart/replay acceptance checks in its source distribution.
The repository consumer below still pins the earlier merged per-tool circuit-breaker
commit, so its exact Git installation reports package metadata `2.0.0a6`. It has not
been repinned to a8, a9, a10 or a11 here. The qualification experiments below are
not completed consumer upgrades. Release verification remains separate from adoption.

## a11 candidate qualification, not adoption

On 2026-08-31, the consumer's local and GitHub main remained
`be56db8476454d6f241a5da7d5e846d92d1bcefb`. A fresh archive of that commit supplied
unchanged tests. The diagnostic consumer wheel from the a10 experiment below was
reused only after verifying its SHA-256:
`6059d41a0c5d539b2988a6ee71fac4cd30661c163992245039e768b9370345be`.
It was not rebuilt or represented as the older historical release artifact.

A fresh Python 3.11.9 environment installed the actual published Core a11 wheel,
SHA-256 `dc694e104dcd979db1515b607ef3ee7e2e05d6af39bb159703351f64493d653f`,
and that consumer wheel with `python -m pip --isolated install --no-index --no-deps`.
Guard and Orchestration were separately installed from the exact Git pins below;
their installed `direct_url.json` commit IDs matched. Core and consumer imports
resolved to this environment's `site-packages`. Test tooling was pytest 8.4.2,
pytest-asyncio 1.4.0 and pytest-cov 7.1.0. Dependency/tool acquisition used the network;
the two-wheel installation did not. This intentionally overrides the untouched
consumer manifest and is not a fresh installation of its declared dependency set.

From the archived consumer root, using that environment's Python:

```text
python -m pip check  -> no broken requirements (not a Git-pin provenance check)
python -I -m pytest -> 37 passed, 1 failed; 91.03% installed-consumer branch coverage
```

The sole failure was `test_pinned_core_version_is_compatible`: it expects
`2.0.0a6`, while the candidate correctly reports `2.0.0a11`. No test was skipped,
patched, xfailed or version-spoofed. Existing behavioral tests passed, including
redaction, privacy, policy, cancellation, task, rate/circuit, replay and filesystem
contracts. This does not prove modern MCP consumer support; its factory still
selects the legacy protocol. The original consumer worktree remained clean and
unchanged. No private implementation was copied into this repository.

Read-only reinspection of consumer run `31460072311` found three failed jobs with
zero executed steps. Check-run `94616059885` still carries GitHub's account
payments/spending-limit annotation. That is evidence about the recorded run,
not proof of the account's current billing state. No new consumer run was dispatched.
Current declared-install compatibility and fresh Python 3.11-3.13 CI remain open.

Desktop automation also failed before window inspection, including one reset/retry,
with `failed to write kernel assets` / Windows error 3. No current desktop, sign-in,
trust or approval state was observed. Earlier configuration discovery below is
historical evidence only; SDK acceptance is not desktop consent acceptance.

## Owner-session handoff for the consumer

The following bounded prompt is intended for a separate session in the consumer
repository. It has not been dispatched and does not authorize billing changes,
production deployment or publication of private source:

> Work only in `samsarix-integration-examples`; preserve unrelated changes and keep
> its visibility private. Audit the current manifest and tests before editing.
> Upgrade only Core to exact commit
> `d9ae73cf09e17a6ed3a6d2f092645dcac4743e22` (published `v2.0.0a11`), updating the
> matching package-version expectation to `2.0.0a11`. Preserve the existing Guard
> and Orchestration pins unless a separately demonstrated incompatibility requires
> owner review. Keep the consumer's legacy MCP default; do not claim modern support
> merely because Core supports it. Install the declared dependencies in a fresh
> environment and check installed Git commit identities, versions and import paths.
> Run `python -m pip check`, `python -m ruff check .`, `python -m mypy`,
> `python -m pytest`, `python -m bandit -q -r src`, `python -m build` and
> `python -m twine check --strict dist/*`. The current suite has 38 tests: retain
> its privacy, cancellation, task, replay and filesystem assertions. Verify both
> installed CLI help paths and the documented redaction MCP journey from outside
> the checkout against the built wheel. Obtain fresh consumer Python 3.11-3.13
> CI evidence; recorded jobs stopped before checkout with a billing annotation.
> Ask the owner to resolve any account gate without changing spending or payment
> settings yourself. Commit/push/merge only under the owner session's authorization
> and after required checks actually pass. Record exact commits and results;
> never copy private implementation into public Core documentation.

For desktop acceptance, the operator must handle sign-in, server trust and tool
approval personally. Then record the client/version, consumer/Core commits and
negotiated protocol, discovery, one approved redaction and its artifact, cancellation
without an artifact, and a subsequent successful request. Record only non-sensitive
outcomes: no real source documents, tokens or workspace paths. If automation cannot
initialize, restore that facility or perform the checklist manually; do not bypass
the client's security prompts. These actions are acceptance work, not a request to
add another Core feature.

## a10 candidate qualification, not adoption

An unchanged archive of consumer commit `be56db8476454d6f241a5da7d5e846d92d1bcefb`
was built in a fresh temporary directory. The resulting local wheel SHA-256 was
`6059d41a0c5d539b2988a6ee71fac4cd30661c163992245039e768b9370345be`; it is a
new diagnostic build, not the older artifact recorded below. An attempted reuse of
a cached wheel was stopped when its hash differed from that historical record.
No cached or immutable artifact was replaced.

A fresh Python 3.11.9 environment installed the unchanged consumer wheel and the
actual published Core a10 wheel, SHA-256
`e84b26935ab9f73a7c632085ec9401256ffb8be0d107ce456a2e6604fec9d638`, offline with
`--no-index --no-deps`. Guard and Orchestration were installed separately from the
exact public commits in the table below; their installed `direct_url.json` commit
identities were verified. Both consumer and Core imports resolved to that environment's
`site-packages`, not either source checkout. The consumer's original dependency manifest
was not edited: this is an intentional candidate override, not its declared install.
`pip check` passed but does not prove an exact Git provenance pin was honored.

Running `python -I -m pytest` on the unchanged archived consumer tests yielded
**37 passed, 1 failed**, with 91.03% installed-consumer branch coverage. The sole
failure requires Core's old `2.0.0a6` version; the installed candidate correctly
reported `2.0.0a10`. No test was skipped, patched, xfailed or version-spoofed. The
behavioral checks exercised the real redaction, policy, rate/circuit, cancellation,
task, replay and filesystem contracts. This narrows upgrade work but does not prove
modern consumer support: its unchanged factory uses the legacy MCP protocol.

The original consumer worktree remained clean at the same commit. Its owner-side
upgrade still needs a manifest repin, matching version expectation, fresh declared
installation and its own CI/review. No private implementation was copied into Core,
no consumer visibility was changed, and this test is not added as a credential-dependent
public CI requirement.

## Privacy-first redaction MCP consumer

Repository:
[Deathcharge/samsarix-integration-examples](https://github.com/Deathcharge/samsarix-integration-examples)

| Evidence | Value |
| --- | --- |
| Core contract commit | `2744d69eb58aef8412d15fbee9485b6d22eb30a5` |
| Core package metadata at pinned commit | `2.0.0a6` |
| Consumer merge commit | `be56db8476454d6f241a5da7d5e846d92d1bcefb` |
| Consumer pull request | [samsarix-integration-examples#15](https://github.com/Deathcharge/samsarix-integration-examples/pull/15) |
| Consumer package version | `0.2.12` |
| Integration Guard provenance | [`samsarix-integration-guard`](https://github.com/Deathcharge/samsarix-integration-guard) `0.2.0` at `1aa711d89eaedcc396f0cd6eb416fb4253da3f5e` |
| Orchestration provenance | [`samsarix-agent-orchestration`](https://github.com/Deathcharge/samsarix-agent-orchestration) `0.1.0` at `0dfc050cf9a4582c9fa8d34d74b1ca97d43c9005` |
| Declared consumer Python | 3.11-3.13 |
| Executed consumer Python in this record | 3.11.9 fresh exact-pin editable environment and clean installed wheel |
| Compatibility owner | Samsarix LLC |
| Support level | Best effort; no SLA |

The consumer composes three independently packaged projects through public APIs:
Core provides the bounded MCP runtime, Integration Guard redacts sensitive JSON,
and Orchestration provides checkpointed recovery and idempotency. A client may
name one JSON file in a configured inbox and one artifact filename. It cannot
supply an absolute path or path separator, linked files are rejected, conflicting
artifacts are not replaced, and successful MCP results contain metadata rather
than document content or local paths. Its public `RedactionResult` `TypedDict`
also proves Core's exact, closed output schemas and result validation from an
independently packaged consumer. A deliberately blocked redaction call additionally
proves MCP client cancellation through the public stdio bridge: the consumer receives
no response for the cancelled request, the asynchronous tool stops, no output
artifact is published, runtime metrics return to zero in-flight calls with one
cancellation recorded, and a subsequent `tools/list` request succeeds on the same
connection. When the client provides a progress token, a successful call emits exactly
two token-correlated, strictly increasing, content-free phases before its terminal
response. Cancellation emits only the completed validation phase, closes progress before
tool cleanup, and refuses the cleanup-time update. The consumer asserts that neither
source secrets nor resolved workspace paths occur in protocol output. Operational
logging defaults to `warning`, so a successful event is suppressed until the client
selects `info`. The accepted event contains only the public tool name, invocation ID,
status, and duration; it follows both progress phases and precedes the response. A
cancelled call emits no terminal log.

The consumer now passes a host-owned lifecycle handler into Core's public runtime API.
One real, policy-gated redaction invocation produces exactly one `started` and one
`success` event with the same random invocation identifier, the public tool name, and a
terminal duration. The consumer serializes those events and proves that seeded source
secrets, the source and output filenames, the private run identifier, and the resolved
workspace path are absent. This is provider-neutral process-local observation, not a
durable audit log, trace exporter, or claim that arbitrary downstream handlers are safe.

The same public factory accepts an optional `ToolRateLimit` and applies it only to the
exact redaction registration. A consumer-owned test admits one real policy-gated
redaction, then immediately calls it again through the same runtime. The first call
succeeds and publishes its artifact; the second returns status `rate_limited`, safe code
`tool_rate_limited`, and a numeric retry delay without executing or publishing another
artifact. The final content-free metrics report one success and one rate-limited call,
and serialized results contain neither seeded private values nor the workspace path.
This proves one process-local tool quota boundary, not distributed coordination,
per-tenant accounting, authorization, or a service-level quota.

The factory independently accepts an optional host-owned `ToolCircuitBreaker` for the
same exact registration. A consumer-owned test injects one private downstream failure,
observes safe `tool_failed` protocol output, and verifies the immediate next call returns
status `circuit_open` without pipeline execution or artifact creation. After the recovery
interval, one half-open probe completes a real redaction and closes the circuit. Exact
metrics report one failure, one trip, one open rejection, and one success. Seeded source
values, filenames, run identifiers, failure text, and workspace paths are absent from the
failed and blocked results. This proves process-local dependency protection, not retries,
cross-process coordination, per-tenant isolation, or durable health state.

The consumer adapter now installs a fail-closed host policy through Core's public
`ToolPolicyContext` and `ToolPolicyDecision` API. It admits only the exact redaction
name, version, tags, task mode, safety annotations, and default-filled argument set.
The consumer independently registers a destructive, open-world test tool and proves
that an MCP call reaches status `denied` without executing the tool or reflecting its
private argument. Ordinary and task-augmented redaction journeys still succeed, proving
the policy receives Core's validated, default-filled contract. This is defense in depth,
not caller authentication or evidence of human approval.

The consumer configures Core's direct runtime to admit at most eight non-terminal
invocations. Its contract test lowers that cap to one, admits a real redaction call,
and submits a second call through MCP with seeded private arguments. The second call
returns status `busy` and safe, retryable code `runtime_busy`; the policy evaluation
count remains one, no second tool execution occurs, no private argument is reflected,
and no artifact is created. Cancelling the admitted call returns
`pending_invocations` to zero. This proves process-local load shedding through Core's
public API; that admission fixture alone is not per-client fairness or authorization.

The same consumer redaction tool advertises task support as optional, preserving the
ordinary call and older-client contract. A task-aware MCP `2025-11-25` client receives
an immediate `working` state with a random 128-bit identifier; that state contains no
source name, output name, run id, arguments, result, secret, or workspace path. The
consumer proves `tasks/get`, blocking `tasks/result`, exact structured result retrieval,
and two related-task progress updates. Requested retention is clamped to the
application's fifteen-minute maximum, only eight session-local tasks may be retained,
and unauthenticated `tasks/list` remains unavailable. A blocked task can be cancelled;
the async redaction stops, cleanup-time progress is refused, no artifact is published,
and `tasks/result` retains only Core's generic cancelled result.

A separate consumer-owned synchronous fixture occupies one real worker under a
single-slot runtime. After the caller-visible timeout, the fixture proves the worker,
slot, in-flight gauge, and pending-sync count remain occupied; a second call cannot
start. Zero-wait quiescence and finite-wait shutdown both report `False`, closing the
runtime refuses a third call, and none of those safe errors disclose the private fixture
arguments. After a consumer-controlled release, pending and in-flight work return to
zero and bounded shutdown succeeds. The gated probe exists only in the contract suite
and is not a production redaction tool.

The consumer now ships a portable, workspace-scoped Visual Studio Code MCP
configuration and confined example. At consumer version 0.2.6, the official MCP
Inspector 0.21.2 client discovered
the exact tool schemas and successfully invoked the freshly installed consumer wheel
over stdio; its result and artifact excluded the seeded token, email, and workspace path.
Visual Studio Code 1.131.0 separately opened the sample and discovered the stopped
`samsarixRedaction` server from the expected `.vscode/mcp.json`. That desktop profile
was signed out of Copilot, so no trust prompt or VS Code tool call was accepted. This is
desktop configuration-discovery evidence, not a completed desktop-agent journey.

The consumer's merged
[`pyproject.toml`](https://github.com/Deathcharge/samsarix-integration-examples/blob/be56db8476454d6f241a5da7d5e846d92d1bcefb/pyproject.toml)
is the dependency manifest. It declares
`samsarix-core @ git+https://github.com/Deathcharge/samsarix-core.git@2744d69eb58aef8412d15fbee9485b6d22eb30a5`;
the installed public package reports Core version `2.0.0a6`. The same manifest
records the Guard and Orchestration commits above, and the compatibility test
asserts all three installed package versions.

## Verified contract

The exact-pin consumer contract checks completed locally on Windows in a fresh editable
environment with Python 3.11.9:

```text
python -m ruff check .       -> passed
python -m mypy               -> passed, strict mode
python -m pytest             -> 38 passed, 91.64% branch coverage
python -m bandit -q -r src   -> passed
```

The isolated release build and strict metadata checks separately passed on Python 3.11.9:

```text
python -m build                    -> isolated wheel and sdist passed
python -m twine check <artifacts> -> wheel and sdist passed
```

A fresh virtual environment installed the consumer wheel with dependencies resolved
from their exact public Git commits. Import metadata resolved to consumer `0.2.12` and
Core `2.0.0a6`; the consumer import resolved from the environment's `site-packages`.
Outside the source checkout, both installed CLIs passed their help journeys and the
public factory exposed the optional circuit-breaker dependency control. The exact-pin
test suite separately proved one private failure, fail-fast rejection, and a successful
real recovery redaction. `pip check` reported no broken requirements. Python 3.12 and
3.13 remain declared consumer support, but their
hosted jobs did not execute in this record because the account billing gate stopped the
matrix before checkout.

Final local artifacts were:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `samsarix_integration_examples-0.2.12-py3-none-any.whl` | 19,450 | `b72d61cc67132cdbb7df63be41fdd077a29e3fe9bbbc3673fa7a98c42c74608a` |
| `samsarix_integration_examples-0.2.12.tar.gz` | 42,116 | `8a32e0b79a6bcb4abb593af10562f8cc32d65931a6962edd4532e3cac370b1c4` |

CodeRabbit attached a green high-level status, but its free-plan notice says the pass
provides only a summary and walkthrough; it is not counted as independent line-level
review evidence. The consumer's
[pull-request run](https://github.com/Deathcharge/samsarix-integration-examples/actions/runs/31460008990)
and [post-merge run](https://github.com/Deathcharge/samsarix-integration-examples/actions/runs/31460072311)
did not start their jobs: GitHub attached an account
billing/spending-limit failure before checkout, leaving zero executed steps and
no job logs. That infrastructure failure is not represented as hosted test
evidence. The workflow should be rerun after the account's Billing & plans issue
is resolved.

## Compatibility and rollback

The consumer uses an exact Git commit dependency rather than a moving branch.
Updating Core requires a consumer pull request that reruns the same privacy,
filesystem, protocol, packaging, and version checks. Until Core declares a stable
release line, compatibility is commit-specific.

Rollback is consumer-owned: stop the local MCP process, remove its client
registration, and revert the consumer dependency and adapter commit. Core itself
stores no remote state. After any required evidence retention, the operator may
remove the consumer workspace's generated artifacts and sanitized checkpoints.

## Next adoption signals

- Rerun the consumer Python 3.11-3.13 matrix after GitHub Actions billing is
  restored.
- Complete the signed-in Visual Studio Code server-trust and tool-approval journey;
  workspace configuration discovery and independent Inspector invocation are proven.
- Record an independently operated deployment or downstream repository before
  claiming production adoption.
- Use consumer demand, not framework parity, to decide whether dataclass, enum,
  or constrained-value schemas belong in Core.
