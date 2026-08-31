# Benchmarks

`benchmarks/runtime_benchmark.py` is a dependency-free microbenchmark for the
validated local invocation path. It measures sync and async variants of:

- sequential calls per second;
- mean, p50, and p95 end-to-end invocation latency; and
- one ordered batch's duration and calls per second.

It also repeats the asynchronous sequential path with a constant-time lifecycle
handler, verifies exactly two events per measured/warm-up invocation, and reports that
path separately as `async_sequential_noop_lifecycle`. Compare it with
`async_sequential` on the same run to estimate event construction and callback overhead;
it does not model network export.

The benchmark also repeats that path through a full per-tool token bucket and reports
`async_sequential_full_rate_bucket`. It verifies zero throttled calls, so the comparison
isolates local refill/check overhead rather than retry or downstream behavior.

Run it from an installed development checkout:

```bash
python benchmarks/runtime_benchmark.py --iterations 2000 --batch-size 256
```

`benchmarks/mcp_stdio_benchmark.py` measures aggregate throughput for the complete
in-memory newline parse, MCP dispatch, validation, async tool, and response
serialization path. It validates every structured response and fails if the
configured admission cap rejects a call. Its optional progress mode also validates
the expected notification count and measures the complete progress write path:

```bash
python benchmarks/mcp_stdio_benchmark.py \
  --iterations 2000 \
  --max-concurrency 8 \
  --max-in-flight-requests 64 \
  --progress-updates-per-call 0
```

Use `--progress-updates-per-call 2` for a progress-enabled comparison against the
zero-update baseline. Throughput includes every generated notification and
terminal response. The benchmark accepts at most 1,000 updates per call, matching
the runtime cap it configures.

The command emits JSON with the Python, platform, and Samsarix Core versions so
runs can be retained and compared. Use the same machine, Python build, power mode,
iteration count, and package commit when evaluating a change. Run it several times
after warm-up and compare distributions rather than one best result.

These benchmarks intentionally have no CI performance threshold. Shared runners
are noisy, and a microbenchmark of a no-I/O tool does not predict database,
network, model, or user-visible latency. They are regression evidence for Core's
overhead, not claims about every workload or comparisons with another project.

## Mixed-tool dependency outage

`benchmarks/dependency_outage_benchmark.py` answers a different question: can local
inventory-cache lookups finish while requests to a slow vendor are failing, and how
many calls actually reach that vendor? It uses the real public runtime with two
synthetic async tools, not a network, account, model, or production inventory system.

```bash
python benchmarks/dependency_outage_benchmark.py --vendor-calls 64 --local-calls 32 --vendor-delay-ms 20 --repeats 5
```

The three configurations use the same requests and global concurrency limit of eight:

| Scenario | Vendor concurrency | Circuit breaker |
| --- | --- | --- |
| `global_only` | Shares all eight slots | Off |
| `bulkhead` | At most two slots | Off |
| `bulkhead_circuit` | At most two slots | Opens after the first failure |

The pending-invocation cap is set to the sum of vendor and cache calls in every
scenario so admission rejection cannot masquerade as successful outage containment.

Each repetition creates fresh runtimes and rotates the scenario order. All vendor
requests are submitted first. An event barrier holds the first wave until it fills
the configured vendor capacity; only then are the local-cache requests submitted and
the vendor calls released. Each actual vendor execution waits for the configured
synthetic delay and fails. Cache calls return an independently verified integer result.
This deliberately adversarial finite burst models a saturated failing dependency,
not a steady-state arrival process. There is no warm-up or automatic retry. The circuit
recovery interval exceeds the scenario deadline, so this measures outage containment,
not half-open recovery (covered by the runtime tests and installed-wheel smoke).

The JSON report retains every run, runtime counters, actual vendor executions, peak
vendor concurrency, cohort duration, and separate vendor/cache mean, nearest-rank p50,
p95, and maximum latency. Latency starts at task submission, so it includes event-loop
scheduling and capacity waiting. Cohort duration includes initial submission and the
saturation barrier, but excludes runtime construction, verification, and shutdown.
Environment fields include the exact benchmark-file SHA-256; retain the runtime commit
or wheel digest alongside the report because an alpha version string alone is not an
exact source pin.

The checker fails instead of printing results if outputs, failure/rejection counts,
exception redaction, concurrency, metrics, terminal circuit state, or drained capacity
disagree. The two calls already executing when the guarded circuit opens are expected
to finish failing; all remaining vendor calls must be rejected without execution.
Cancellation and the whole-scenario deadline cancel and await all owned tasks, then
close the runtime. CLI limits bound vendor calls to 8–512, cache calls to 1–512, delay
to 1–100 ms, and repetitions to 1–10. Each scenario has a generous deadline of
`5 + vendor_calls * vendor_delay_ms / 1000` seconds plus bounded cleanup. No timing
ratio or absolute performance threshold is enforced in CI; regression tests check
behavior, including deliberately corrupted results, missing controls and abort cleanup.

### Recorded local evidence (2026-08-31)

The command above was run on Windows/CPython 3.11.9 against Core `2.0.0a7` source at
`6ded14d4a5a1a1754d5d080a8dad763161c19b3d`, with the benchmark added in the accompanying
change and no runtime modifications. The [raw JSON report](../benchmarks/results/dependency-outage-windows-py311-20260831.json)
records all 15 runs and the benchmark digest. These ranges retain all five repetitions;
they are not pooled percentiles or confidence intervals.

| Scenario | Actual vendor executions / 64 | Circuit rejections / 64 | Cache p95 range (ms) | Whole-cohort range (ms) |
| --- | --- | --- | --- | --- |
| Global only | 64 | 0 | 191.51–264.40 | 225.37–292.33 |
| Bulkhead | 64 | 0 | 8.00–14.02 | 958.66–1004.86 |
| Bulkhead + circuit | 2 | 62 | 6.45–11.87 | 31.21–65.36 |

All 32 cache lookups per run returned correct results. Bulkheads limited interference
with the local work, but increased the time to drain all failing vendor calls because
only two could execute concurrently. Adding the breaker avoided 62 vendor executions;
those requests **failed fast**, rather than becoming successful. This distinction is
why the report does not advertise overall calls/second as useful throughput.

The workload illustrates the separate purposes of [bulkhead isolation](https://learn.microsoft.com/en-us/azure/architecture/patterns/bulkhead)
and [circuit breaking](https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker).
The numbers are local synthetic observations, not production SLOs, framework rankings,
or proof that these settings fit an adopter's service. CPU load, timer resolution and
event-loop scheduling affect the requested delay and measurements. This harness does
not measure MCP pipes, HTTP/TLS, real I/O, memory saturation, synchronous workers,
shared multi-process limits, policy overhead, or retries. Use dependency-specific
deadlines and reproduce the scenario with your own workload before selecting limits.
