# Adoption evidence

This record separates package compatibility evidence from production-adoption
claims. Samsarix Core has a merged independent repository consumer; it does not
yet have a documented third-party production deployment, paid customer, usage
volume, or service-level commitment.

The latest published `2.0.0a5` prerelease has independently verified artifacts and
installed-wheel lifecycle behavior. The repository consumer below pins the merged
lifecycle-observability commit immediately before the release metadata commit, so its
exact Git installation reports package metadata `2.0.0a4`. Release verification is not
presented as consumer-adoption evidence.

## Privacy-first redaction MCP consumer

Repository:
[Deathcharge/samsarix-integration-examples](https://github.com/Deathcharge/samsarix-integration-examples)

| Evidence | Value |
| --- | --- |
| Core contract commit | `e20a4e982b24dbc7ff2b5c78714742bfd1ee2f90` |
| Core package metadata at pinned commit | `2.0.0a4` |
| Consumer merge commit | `0455b7a16e0309ba295c0ddd8ad3776d709ea782` |
| Consumer pull request | [samsarix-integration-examples#13](https://github.com/Deathcharge/samsarix-integration-examples/pull/13) |
| Consumer package version | `0.2.10` |
| Integration Guard provenance | [`samsarix-integration-guard`](https://github.com/Deathcharge/samsarix-integration-guard) `0.2.0` at `1aa711d89eaedcc396f0cd6eb416fb4253da3f5e` |
| Orchestration provenance | [`samsarix-agent-orchestration`](https://github.com/Deathcharge/samsarix-agent-orchestration) `0.1.0` at `0dfc050cf9a4582c9fa8d34d74b1ca97d43c9005` |
| Declared consumer Python | 3.11-3.13 |
| Executed consumer Python in this record | 3.14.6 source tree and fresh installed wheel |
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
public API; it is not request-rate limiting, per-client fairness, or authorization.

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
[`pyproject.toml`](https://github.com/Deathcharge/samsarix-integration-examples/blob/0455b7a16e0309ba295c0ddd8ad3776d709ea782/pyproject.toml)
is the dependency manifest. It declares
`samsarix-core @ git+https://github.com/Deathcharge/samsarix-core.git@e20a4e982b24dbc7ff2b5c78714742bfd1ee2f90`;
the installed public package reports Core version `2.0.0a4`. The same manifest
records the Guard and Orchestration commits above, and the compatibility test
asserts all three installed package versions.

## Verified contract

The installed-wheel consumer contract checks completed locally on Windows with Python
3.14.6:

```text
python -m ruff check .       -> passed
python -m mypy               -> passed, strict mode
python -m pytest             -> 36 passed, 91.03% branch coverage from installed wheel
python -m bandit -q -r src   -> passed
```

The isolated release build and metadata checks separately passed on Python 3.14.6:

```text
python -m build                    -> isolated wheel and sdist passed
python -m twine check <artifacts> -> wheel and sdist passed
```

A fresh virtual environment installed the consumer wheel with dependencies resolved
from their exact public Git commits. Import metadata resolved to `0.2.10`, and pip cloned
Core and resolved commit `e20a4e982b24dbc7ff2b5c78714742bfd1ee2f90`.
Outside the source checkout, the installed consumer suite proved both the permitted real
redaction path and safe denial of the out-of-contract tool. Both installed CLIs also
passed their help journeys. The source-tree development run on Python 3.14.6 separately
completed the same 36 tests at 91.64% branch coverage. Python 3.12 and 3.13 remain
declared consumer support, but their hosted jobs did not execute in this record because
the account billing gate stopped the matrix before checkout.

Final local artifacts were:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `samsarix_integration_examples-0.2.10-py3-none-any.whl` | 18,838 | `8cf067bd326d7a565b3879580af0ffa66570e6137ea8b6f389bdf2d119e7af1e` |
| `samsarix_integration_examples-0.2.10.tar.gz` | 39,381 | `169d8ab69d568ada568d7224c2f0f459ee2ee0b7e583738b6195d3e3aa97b398` |

CodeRabbit attached a green high-level status, but its free-plan notice says the pass
provides only a summary and walkthrough; it is not counted as independent line-level
review evidence. The consumer's
[pull-request run](https://github.com/Deathcharge/samsarix-integration-examples/actions/runs/30746005628)
and [post-merge run](https://github.com/Deathcharge/samsarix-integration-examples/actions/runs/30746052161)
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
