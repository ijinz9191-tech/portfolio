# Architecture

`topology.js` validates a synthetic cluster graph. `scheduler.js` creates a topology-aware placement and mutates allocation state only after every capacity constraint passes. `diagnostics.js` turns measured signals into ranked, inspectable hypotheses. `remediation.js` requires a proposed allow-listed action, an approval bound to the exact plan hash, execution evidence and a health verification result. `snapshot.js` binds stored state to a SHA-256 digest.

The scheduler and diagnostic rules are intentionally deterministic so test failures can be reproduced. No external cluster, cloud account or production endpoint is contacted.
