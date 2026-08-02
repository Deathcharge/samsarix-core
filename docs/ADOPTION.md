# Adoption evidence

This record separates package compatibility evidence from production-adoption
claims. Samsarix Core has a merged independent repository consumer; it does not
yet have a documented third-party production deployment, paid customer, usage
volume, or service-level commitment.

## Privacy-first redaction MCP consumer

Repository:
[Deathcharge/samsarix-integration-examples](https://github.com/Deathcharge/samsarix-integration-examples)

| Evidence | Value |
| --- | --- |
| Core contract commit | `1558624ba294f47d59ea1713ac5609ef3122239e` |
| Core package version | `2.0.0a1` |
| Consumer merge commit | `51cc3fb3f1fb4bd484ebef58d2c9ab22acc24623` |
| Consumer pull request | [samsarix-integration-examples#10](https://github.com/Deathcharge/samsarix-integration-examples/pull/10) |
| Consumer package version | `0.2.7` |
| Integration Guard provenance | [`samsarix-integration-guard`](https://github.com/Deathcharge/samsarix-integration-guard) `0.2.0` at `1aa711d89eaedcc396f0cd6eb416fb4253da3f5e` |
| Orchestration provenance | [`samsarix-agent-orchestration`](https://github.com/Deathcharge/samsarix-agent-orchestration) `0.1.0` at `0dfc050cf9a4582c9fa8d34d74b1ca97d43c9005` |
| Declared consumer Python | 3.11-3.13 |
| Executed consumer Python in this record | 3.11.9; extra source-tree pass on 3.14.6 |
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
[`pyproject.toml`](https://github.com/Deathcharge/samsarix-integration-examples/blob/51cc3fb3f1fb4bd484ebef58d2c9ab22acc24623/pyproject.toml)
is the dependency manifest. It declares
`samsarix-core @ git+https://github.com/Deathcharge/samsarix-core.git@1558624ba294f47d59ea1713ac5609ef3122239e`;
the installed public package reports Core version `2.0.0a1`. The same manifest
records the Guard and Orchestration commits above, and the compatibility test
asserts all three installed package versions.

## Verified contract

The installed-wheel consumer contract checks completed locally on Windows with Python
3.11.9:

```text
python -m ruff check .       -> passed
python -m mypy               -> passed, strict mode
python -m pytest             -> 33 passed, 90.85% branch coverage from installed wheel
python -m bandit -q -r src   -> passed
```

The isolated release build and metadata checks separately passed on Python 3.14.6:

```text
python -m build                    -> isolated wheel and sdist passed
python -m twine check <artifacts> -> wheel and sdist passed
```

A fresh virtual environment installed the consumer wheel with dependencies
resolved from their exact public Git commits. Import metadata resolved to `0.2.7`
and retained the exact Core commit requirement. Outside the source checkout, the
installed `samsarix-redaction-mcp` CLI completed a real task-augmented redaction over
stdio: initialize, discovery, immediate task creation, blocking result retrieval, and
terminal status. It published a sanitized artifact, emitted exactly two related-task
progress notifications, and exposed neither the three seeded secrets nor the resolved
workspace path in protocol output. Both installed CLIs also passed their help journeys.
The source-tree development run on Python 3.14.6 separately completed the same 33 tests
at 91.47% branch coverage. Python 3.12 and 3.13 remain declared consumer support, but
their hosted jobs did not execute in this record because the account billing gate stopped
the matrix before checkout.

Final local artifacts were:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `samsarix_integration_examples-0.2.7-py3-none-any.whl` | 18,303 | `1c538ac89b2ea878b1ef0cd8ee0628cef6bcc4745efc39cb42927018d1770896` |
| `samsarix_integration_examples-0.2.7.tar.gz` | 36,469 | `807f33bd857ec7918e4b0a0747472638120a618ea977323c86d4808d3ffd4cf5` |

CodeRabbit attached a green high-level status, but its free-plan notice says the pass
provides only a summary and walkthrough; it is not counted as independent line-level
review evidence. The consumer's
[pull-request](https://github.com/Deathcharge/samsarix-integration-examples/actions/runs/30736315532)
and [post-merge](https://github.com/Deathcharge/samsarix-integration-examples/actions/runs/30736368378)
GitHub Actions runs
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
