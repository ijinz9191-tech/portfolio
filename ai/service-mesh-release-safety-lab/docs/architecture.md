# Architecture

`ReleaseController` owns release state and fail-closed gates. The caller supplies normalized synthetic metrics that correspond to Prometheus-style error rate, p99 latency, and resource saturation. Each healthy observation advances one configured mesh weight across all clusters. Any breach atomically returns traffic to zero and marks every cluster rolled back.

`EvidenceLedger` records decisions in an append-only SHA-256 chain. The hash covers the sequence, event type, payload, and preceding hash so mutation or reordering fails verification.

Adapters are intentionally outside the lab. A production integration would authenticate to Kubernetes/Istio and Prometheus, bind observations to a deployment revision, and persist the evidence in durable storage.
