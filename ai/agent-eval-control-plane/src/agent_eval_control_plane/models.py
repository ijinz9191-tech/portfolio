from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ValidationError(ValueError):
    pass


def _strings(value: Any, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValidationError(f"{field} must be a list of strings")
    return tuple(item.strip() for item in value if item.strip())


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    suite: str
    prompt: str
    required_facts: tuple[str, ...]
    forbidden_terms: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    max_tool_calls: int
    latency_budget_ms: int
    cost_budget_units: float

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EvaluationCase":
        if not isinstance(raw, dict):
            raise ValidationError("case must be an object")
        case_id = str(raw.get("case_id", "")).strip()
        suite = str(raw.get("suite", "")).strip()
        prompt = str(raw.get("prompt", "")).strip()
        if not case_id or not suite or not prompt:
            raise ValidationError("case_id, suite and prompt are required")
        max_calls = raw.get("max_tool_calls", 8)
        latency = raw.get("latency_budget_ms", 5000)
        cost = raw.get("cost_budget_units", 1.0)
        if not isinstance(max_calls, int) or max_calls < 0:
            raise ValidationError("max_tool_calls must be a non-negative integer")
        if not isinstance(latency, int) or latency <= 0:
            raise ValidationError("latency_budget_ms must be a positive integer")
        if not isinstance(cost, (int, float)) or cost < 0:
            raise ValidationError("cost_budget_units must be non-negative")
        return cls(
            case_id=case_id,
            suite=suite,
            prompt=prompt,
            required_facts=_strings(raw.get("required_facts"), "required_facts"),
            forbidden_terms=_strings(raw.get("forbidden_terms"), "forbidden_terms"),
            allowed_tools=_strings(raw.get("allowed_tools"), "allowed_tools"),
            max_tool_calls=max_calls,
            latency_budget_ms=latency,
            cost_budget_units=float(cost),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "suite": self.suite,
            "prompt": self.prompt,
            "required_facts": list(self.required_facts),
            "forbidden_terms": list(self.forbidden_terms),
            "allowed_tools": list(self.allowed_tools),
            "max_tool_calls": self.max_tool_calls,
            "latency_budget_ms": self.latency_budget_ms,
            "cost_budget_units": self.cost_budget_units,
        }


@dataclass(frozen=True)
class Step:
    seq: int
    kind: str
    name: str
    status: str
    duration_ms: int

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Step":
        if not isinstance(raw, dict):
            raise ValidationError("each step must be an object")
        seq = raw.get("seq")
        duration = raw.get("duration_ms", 0)
        kind = str(raw.get("kind", "")).strip()
        name = str(raw.get("name", "")).strip()
        status = str(raw.get("status", "")).strip()
        if not isinstance(seq, int) or seq < 1:
            raise ValidationError("step seq must be a positive integer")
        if kind not in {"model", "retrieval", "tool"}:
            raise ValidationError("step kind must be model, retrieval or tool")
        if not name or status not in {"ok", "error", "blocked"}:
            raise ValidationError("step name and a valid status are required")
        if not isinstance(duration, int) or duration < 0:
            raise ValidationError("duration_ms must be non-negative")
        return cls(seq, kind, name, status, duration)

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class RunTrace:
    run_id: str
    case_id: str
    output: str
    latency_ms: int
    cost_units: float
    evidence_refs: tuple[str, ...]
    steps: tuple[Step, ...]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RunTrace":
        if not isinstance(raw, dict):
            raise ValidationError("trace must be an object")
        run_id = str(raw.get("run_id", "")).strip()
        case_id = str(raw.get("case_id", "")).strip()
        output = raw.get("output")
        latency = raw.get("latency_ms")
        cost = raw.get("cost_units")
        if not run_id or not case_id or not isinstance(output, str) or not output.strip():
            raise ValidationError("run_id, case_id and non-empty output are required")
        if not isinstance(latency, int) or latency < 0:
            raise ValidationError("latency_ms must be non-negative")
        if not isinstance(cost, (int, float)) or cost < 0:
            raise ValidationError("cost_units must be non-negative")
        raw_steps = raw.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValidationError("steps must be a non-empty list")
        steps = tuple(Step.from_dict(item) for item in raw_steps)
        if [step.seq for step in steps] != list(range(1, len(steps) + 1)):
            raise ValidationError("step sequence must be contiguous and start at 1")
        return cls(
            run_id=run_id,
            case_id=case_id,
            output=output.strip(),
            latency_ms=latency,
            cost_units=float(cost),
            evidence_refs=_strings(raw.get("evidence_refs"), "evidence_refs"),
            steps=steps,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "case_id": self.case_id,
            "output": self.output,
            "latency_ms": self.latency_ms,
            "cost_units": self.cost_units,
            "evidence_refs": list(self.evidence_refs),
            "steps": [step.as_dict() for step in self.steps],
        }
