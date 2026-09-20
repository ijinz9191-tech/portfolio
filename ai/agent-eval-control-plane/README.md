# Agent Eval Control Plane

A dependency-free Python reference implementation for evaluating synthetic AI Agent traces before release. It turns an Agent run into inspectable quality, policy, latency and cost checks, persists immutable evidence in SQLite, and exposes a read-only report API.

## Problem

An AI Agent can return a plausible answer while using an unapproved tool, omitting evidence, exceeding operational budgets or hiding a failed step. A release gate needs to evaluate the answer and its execution path together.

## Implemented

- Versioned evaluation cases with required facts, forbidden terms, approved tools and budgets
- Strict ordered trace schema for retrieval, tool and model steps
- Deterministic output, evidence, tool-policy, step-health, latency and cost checks
- Fail-closed suite gate with explicit safety failures
- SQLite evidence store with idempotent IDs and conflict detection
- Read-only HTTP reports for health, run evidence and suite gates
- CLI demo, evaluation and gate commands
- Normal and failure-path tests using real temporary SQLite, loopback HTTP and subprocess CLI

## Quick verification

```powershell
.\verify.ps1
```

No package download is required. Python 3.11 or newer is sufficient.

## Scope and provenance

All prompts, traces, runbooks and results are synthetic. The project does not call a production model, cloud API or company system and does not claim production LLMOps experience. The user supplied the goal and career materials; AI-assisted tooling implemented and tested this public reference project.

See [architecture](docs/architecture.md) and [runbook](docs/runbook.md).
