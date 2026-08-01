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

The command emits JSON with the Python, platform, and Samsarix Core versions so
runs can be retained and compared. Use the same machine, Python build, power mode,
iteration count, and package commit when evaluating a change. Run it several times
after warm-up and compare distributions rather than one best result.

This benchmark intentionally has no CI performance threshold. Shared runners are
noisy, and a microbenchmark of a no-I/O tool does not predict database, network,
model, or user-visible latency. It is regression evidence for runtime overhead,
not a claim about every workload or a comparison with another project.
