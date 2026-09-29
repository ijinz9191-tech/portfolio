# Service Mesh Release Safety Lab

A dependency-free Node.js 24 control plane that rehearses safe multi-cluster service-mesh releases with progressive traffic shifts, SLO gates, security checks, automatic rollback, and tamper-evident evidence.

## Why it exists

Large Kubernetes fleets need repeatable release decisions. A successful deployment command is insufficient when error rate, latency, saturation, security, and remaining error budget are unknown. This lab models the decision boundary without claiming access to a production cluster.

## Capabilities

- Validates two or more unique clusters, an approval token, and remaining error budget before release.
- Applies deterministic 5% → 25% → 50% → 100% traffic shifts across every cluster.
- Stops and rolls back on error-rate, p99 latency, resource saturation, or security-policy breaches.
- Optional strict per-cluster telemetry mode requires a fresh sample from every configured cluster before advancing. A breach in one cluster rolls back the whole release, even when another cluster is healthy. Missing, extra, stale and future-dated cluster samples cannot advance traffic.
- Records start, observations, decisions, traffic changes, completion, and rollback in a SHA-256 hash chain.
- Includes 25 normal and failure-path tests with only synthetic data.

## Run

```powershell
npm test
npm run demo
npm run verify
```

The demo prints JSON for a healthy checkout-service rollout. It does not require Kubernetes, cloud credentials, or network access.

For multi-cluster rehearsal, construct `ReleaseController` with `requireClusterSamples: true` and an optional `maxSampleAgeMs`. Then call `observe(releaseId, { clusterSamples: { 'seoul-a': { errorRate, p99LatencyMs, saturation, observedAt }, 'seoul-b': { ... } } })`. `observedAt` is an ISO-8601 timestamp. The default aggregate mode remains available for older local fixtures, but strict mode is the safer multi-cluster decision path.

## Boundaries

This is a deterministic local engineering lab. It does not claim production Toss, Istio, Kubernetes, Prometheus, or financial-system operation. The interfaces mirror the decision inputs that a real adapter could obtain from a service mesh and monitoring stack.

See [architecture](docs/architecture.md), [runbook](docs/runbook.md), and [verification](docs/verification.md).
