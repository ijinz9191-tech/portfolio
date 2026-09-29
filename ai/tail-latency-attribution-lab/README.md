# Tail Latency Attribution Lab

An offline Python lab for reviewing **synthetic** shopping request traces. It calculates nearest-rank p95 request latency and points to the span with the largest exclusive wall time in each slow trace. A parent span's overlapping direct child intervals are merged before subtraction; concurrent children are not double counted.

```powershell
conda run -n base python -B -m unittest discover -s tests -v
conda run -n base python -B latency.py samples/shopping.json
```

The input requires one root per request, valid parent links, nested time intervals and bounded integer milliseconds. Bad, cyclic, orphaned or impossible traces are rejected. The SHA-256 digest is stable across trace and span ordering. Outputs are **investigation candidates** only. A small sample p95 is not a production SLO measurement, and exclusive span time is not a causal performance proof. No live service or private employer data is used.
