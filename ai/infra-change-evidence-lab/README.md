# Infrastructure Change Evidence Lab

A dependency-free Python reference project for validating synthetic enterprise infrastructure changes before execution. It checks inventory integrity, dependency blast radius, maintenance windows, execution and rollback plans, approval quorum, downtime budgets and emergency controls, then stores immutable evidence in SQLite.

## Problem

Server and network changes fail when ownership, dependencies, rollback, approval or impact are discovered only during an outage. This project turns a proposed change and a versioned synthetic inventory into deterministic, reviewable evidence before an operator touches infrastructure.

## Implemented

- Inventory checks for asset existence, ownership, lifecycle state and duplicate IPs
- Dependency-aware blast-radius calculation and scope validation
- Time-zone-aware maintenance windows capped at four hours
- Ordered execution and rollback plan requirements
- Risk-based unique approval quorum and production downtime budget
- Emergency-change ticket and approval controls
- SHA-256 evidence binding the input inventory, request and checks
- SQLite idempotency with conflicting change ID rejection
- Read-only HTTP health, summary and decision endpoints
- CLI and normal/failure-path tests with real temporary SQLite and loopback HTTP

## Quick verification

```powershell
.\verify.ps1
```

Python 3.11 or newer is sufficient. No package download is required.

## Scope and provenance

All assets, addresses, owners, approvals and changes are synthetic. The project does not connect to Samsung Welstory or any company system and does not claim Cisco, Windows or IT asset-management production experience. It demonstrates a transferable approach built from verified Linux, deployment, CI/CD and observability experience. The user supplied the goal and career evidence; AI-assisted tooling implemented and tested this public reference project.

See [architecture](docs/architecture.md) and [runbook](docs/runbook.md).
