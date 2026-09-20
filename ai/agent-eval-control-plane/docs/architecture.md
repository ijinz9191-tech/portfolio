# Architecture

```text
Versioned evaluation case
        +
Synthetic Agent run trace
        ↓
Schema and sequence validation
        ↓
Deterministic quality / policy / latency / cost checks
        ↓
Immutable run ID + SQLite evidence
        ↓
Suite release gate → read-only HTTP report
```

The control plane separates the output being judged from the evidence used to judge it. A case fixes required facts, forbidden terms, allowed tools and operational budgets. A trace records ordered retrieval, tool and model steps. The evaluator produces individual checks and a fail-closed suite gate.

This reference implementation does not call an LLM, Kubernetes or a cloud service. It uses synthetic fixtures so every result is reproducible on a local Python runtime.
