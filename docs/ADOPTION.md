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
| Core contract commit | `04cf5ba7ca7eb2defcb946f538d62291762db109` |
| Core package version | `2.0.0a1` |
| Consumer merge commit | `f1bcbe1157865e99332caae3c302a2b25d0ed1ed` |
| Consumer pull request | [samsarix-integration-examples#8](https://github.com/Deathcharge/samsarix-integration-examples/pull/8) |
| Consumer package version | `0.2.5` |
| Integration Guard provenance | [`samsarix-integration-guard`](https://github.com/Deathcharge/samsarix-integration-guard) `0.2.0` at `1aa711d89eaedcc396f0cd6eb416fb4253da3f5e` |
| Orchestration provenance | [`samsarix-agent-orchestration`](https://github.com/Deathcharge/samsarix-agent-orchestration) `0.1.0` at `0dfc050cf9a4582c9fa8d34d74b1ca97d43c9005` |
| Supported consumer Python | 3.11-3.13 |
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

A separate consumer-owned synchronous fixture occupies one real worker under a
single-slot runtime. After the caller-visible timeout, the fixture proves the worker,
slot, in-flight gauge, and pending-sync count remain occupied; a second call cannot
start. Zero-wait quiescence and finite-wait shutdown both report `False`, closing the
runtime refuses a third call, and none of those safe errors disclose the private fixture
arguments. After a consumer-controlled release, pending and in-flight work return to
zero and bounded shutdown succeeds. The gated probe exists only in the contract suite
and is not a production redaction tool.

The consumer's merged
[`pyproject.toml`](https://github.com/Deathcharge/samsarix-integration-examples/blob/f1bcbe1157865e99332caae3c302a2b25d0ed1ed/pyproject.toml)
is the dependency manifest. It declares
`samsarix-core @ git+https://github.com/Deathcharge/samsarix-core.git@04cf5ba7ca7eb2defcb946f538d62291762db109`;
the installed public package reports Core version `2.0.0a1`. The same manifest
records the Guard and Orchestration commits above, and the compatibility test
asserts all three installed package versions.

## Verified contract

The consumer suite completed locally on Windows with Python 3.11.9:

```text
python -m ruff check .       -> passed
python -m mypy               -> passed, strict mode
python -m pytest -q          -> 30 passed, 91.35% branch coverage
python -m bandit -q -r src   -> passed
python -m build              -> isolated wheel and sdist passed
python -m twine check <artifacts> -> wheel and sdist passed
```

A fresh virtual environment installed the consumer wheel with dependencies
resolved from their exact public Git commits. Import metadata resolved to `0.2.5`
and retained the exact Core commit requirement. Outside the source checkout, the
installed `samsarix-redaction-mcp` CLI completed a real redaction over stdio,
published a sanitized artifact, emitted exactly two token-correlated progress
notifications followed by one content-free operational log and the terminal
response, and exposed neither the seeded secret nor the resolved workspace path in
protocol output.

Final local artifacts were:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `samsarix_integration_examples-0.2.5-py3-none-any.whl` | 17,519 | `31abff6dd15ff25771d85a30600b36d25145db5aa62a520b75f4a2b527cc3d98` |
| `samsarix_integration_examples-0.2.5.tar.gz` | 30,362 | `498851085c74c0a0c59fe13149a779941fa68a51d44ff1d8ac87514496a505f4` |

CodeRabbit attached a green high-level status, but its quota warning states that a
comprehensive review did not start; it is not counted as independent line-level review
evidence. The consumer's
[pull-request](https://github.com/Deathcharge/samsarix-integration-examples/actions/runs/30732577364)
and [post-merge](https://github.com/Deathcharge/samsarix-integration-examples/actions/runs/30732604781)
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
- Exercise the same contract from an independently operated desktop client.
- Record an independently operated deployment or downstream repository before
  claiming production adoption.
- Use consumer demand, not framework parity, to decide whether dataclass, enum,
  or constrained-value schemas belong in Core.
