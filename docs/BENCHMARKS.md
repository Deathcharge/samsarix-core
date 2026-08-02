# Benchmarks

`benchmarks/runtime_benchmark.py` is a dependency-free microbenchmark for the
validated local invocation path. It measures sync and async variants of:

- sequential calls per second;
- mean, p50, and p95 end-to-end invocation latency; and
- one ordered batch's duration and calls per second.

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
terminal response.

The command emits JSON with the Python, platform, and Samsarix Core versions so
runs can be retained and compared. Use the same machine, Python build, power mode,
iteration count, and package commit when evaluating a change. Run it several times
after warm-up and compare distributions rather than one best result.

These benchmarks intentionally have no CI performance threshold. Shared runners
are noisy, and a microbenchmark of a no-I/O tool does not predict database,
network, model, or user-visible latency. They are regression evidence for Core's
overhead, not claims about every workload or comparisons with another project.
