"""32개 실습을 독립 프로세스에서 실행하고 현재 소스와 검증 결과를 연결한다."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
REGISTRY = WORKSPACE / "ai" / "quality" / "projects.json"
EXCLUDED = {".git", "node_modules", "__pycache__", "artifacts", "build", ".build"}
SOURCE_EXTENSIONS = {".py", ".js", ".mjs", ".java", ".json", ".toml", ".md", ".sql"}
PYTHON_TEST = """
import json, sys, unittest
sys.path[:0] = ['.', 'src']
suite = unittest.defaultTestLoader.discover('tests', pattern='test_*.py')
count = suite.countTestCases()
result = unittest.TextTestRunner(verbosity=2).run(suite)
print('QUALITY_RESULT:' + json.dumps({'tests': result.testsRun,
    'failures': len(result.failures) + len(result.errors), 'skipped': len(result.skipped)}))
sys.exit(0 if count > 0 and result.wasSuccessful() and not result.skipped else 1)
"""


def source_manifest(directory: Path) -> list[dict[str, str]]:
    """생성물·DB를 제외하고 상대 경로와 내용으로 재현 가능한 소스 지문을 만든다."""
    return [
        {
            "path": path.relative_to(directory).as_posix(),
            "sha256": hashlib.sha256(
                path.read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest(),
        }
        for path in sorted(directory.rglob("*"))
        if path.is_file()
        and path.suffix in SOURCE_EXTENSIONS
        and not EXCLUDED.intersection(path.relative_to(directory).parts)
    ]


def execute(command: list[str], directory: Path, timeout: int) -> tuple[int, str]:
    try:
        result = subprocess.run(
            command,
            check=False,
            cwd=directory,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        return result.returncode, result.stdout + "\n" + result.stderr
    except subprocess.TimeoutExpired:
        return 124, "정해진 검사 시간 초과"
    except OSError as error:
        return 127, f"런타임 실행 실패: {error.__class__.__name__}"


def parse_java_summary(output: str) -> tuple[int, int]:
    """개별 PASS 제목의 숫자 대신 마지막 종료 요약만 집계한다."""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return 0, 0
    gateway = re.fullmatch(r"RESULT (\d+) passed, (\d+) failed", lines[-1])
    if gateway:
        passed, failed = map(int, gateway.groups())
        return passed + failed, failed
    delivery = re.fullmatch(r"PASS (\d+)/(\d+)", lines[0])
    if delivery:
        passed, total = map(int, delivery.groups())
        titles = lines[1:]
        if (
            0 <= passed <= total
            and all(line.startswith("PASS ") for line in titles)
            and (not titles or len(titles) == passed)
        ):
            return total, total - passed
    return 0, 0


def run_project(project: dict, root: Path, args: argparse.Namespace) -> dict:
    directory = root / "ai" / project["id"]
    started = time.monotonic()
    sources = source_manifest(directory)
    fingerprint = hashlib.sha256(
        json.dumps(sources, sort_keys=True).encode()
    ).hexdigest()
    stages = []
    count = failures = skipped = 0
    output = ""
    code = 127
    runtime = project["runtime"]
    if runtime == "python":
        command = [sys.executable, "-X", "utf8", "-c", PYTHON_TEST]
        code, output = execute(command, directory, args.timeout)
        match = re.search(r"QUALITY_RESULT:(\{[^\n]+\})", output)
        if match:
            summary = json.loads(match[1])
            count, failures, skipped = (
                summary[key] for key in ("tests", "failures", "skipped")
            )
        stages.append({"stage": "unittest", "exit_code": code})
    elif runtime == "node":
        tests = sorted(
            [*directory.glob("tests/*.test.js"), *directory.glob("tests/*.test.mjs")]
        )
        command = [
            args.node,
            "--test",
            "--test-isolation=none",
            "--test-reporter=tap",
            *map(str, tests),
        ]
        code, output = (
            execute(command, directory, args.timeout) if tests else (2, "미검출 테스트")
        )
        for label in ("tests", "fail", "skipped"):
            match = re.search(rf"^# {label} (\d+)\s*$", output, re.MULTILINE)
            if match:
                if label == "tests":
                    count = int(match[1])
                elif label == "fail":
                    failures = int(match[1])
                else:
                    skipped = int(match[1])
        stages.append({"stage": "node-test", "exit_code": code})
    elif runtime == "java":
        build = (
            WORKSPACE
            / ".tooling"
            / "build"
            / root.name
            / project["id"]
            / fingerprint[:16]
        )
        build.mkdir(parents=True, exist_ok=True)
        files = [
            str(directory / item["path"])
            for item in sources
            if item["path"].endswith(".java")
        ]
        code, output = execute(
            [args.javac, "--release", "21", "-d", str(build), *files],
            directory,
            args.timeout,
        )
        stages.append({"stage": "javac-release-21", "exit_code": code})
        if code == 0:
            main = (
                "lab.GatewayTest"
                if project["id"] == "ai-inference-gateway"
                else "lab.delivery.DeliveryCommandLedgerTest"
            )
            code, output = execute(
                [args.java, "-ea", "-cp", str(build), main], directory, args.timeout
            )
            stages.append({"stage": "java-assertions", "exit_code": code})
            count, failures = parse_java_summary(output)
    passed = code == 0 and count > 0 and failures == 0 and skipped == 0
    unchanged = sources == source_manifest(directory)
    passed = passed and unchanged
    record = {
        "id": project["id"],
        "title": project["title"],
        "runtime": runtime,
        "status": "PASS" if passed else "FAIL",
        "tests": count,
        "failures": failures,
        "skipped": skipped,
        "stages": stages,
        "source_hash": fingerprint,
        "source_unchanged_during_run": unchanged,
        "sources": sources,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    if not passed:
        record["failure_output"] = (
            output[-8000:]
            .replace(str(root), "<ROOT>")
            .replace(str(WORKSPACE), "<WORKSPACE>")
        )
    print(
        f"{record['status']:4} {project['id']}: {count} tests; {record['elapsed_seconds']}s",
        flush=True,
    )
    if not passed:
        print(record.get("failure_output", "검사 중 소스 변경"), flush=True)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=WORKSPACE)
    parser.add_argument("--projects", nargs="*")
    parser.add_argument("--node", default=shutil.which("node") or "node")
    parser.add_argument("--java", default=shutil.which("java") or "java")
    parser.add_argument("--javac", default=shutil.which("javac") or "javac")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["projects"]
    ids = [project["id"] for project in registry]
    if (
        len(ids) != 32
        or len(set(ids)) != 32
        or any(not re.fullmatch(r"[a-z0-9-]+", value) for value in ids)
    ):
        parser.error("32개 프로젝트 목록에 누락·중복·잘못된 경로가 있습니다")
    if args.projects and set(args.projects) - set(ids):
        parser.error("등록되지 않은 프로젝트입니다")
    root = args.root.resolve()
    selected = [
        project
        for project in registry
        if not args.projects or project["id"] in args.projects
    ]
    missing = [
        project["id"]
        for project in selected
        if not (root / "ai" / project["id"] / "README.md").is_file()
    ]
    if missing:
        parser.error("프로젝트 경로가 없습니다: " + ", ".join(missing))
    records = [run_project(project, root, args) for project in selected]
    result = {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version.split()[0],
        "status": "PASS" if all(r["status"] == "PASS" for r in records) else "FAIL",
        "project_count": len(records),
        "tests": sum(r["tests"] for r in records),
        "projects": records,
        "scope": "합성 자료·독립 로컬 프로세스 검사. 운영 성과·공인 코딩테스트 등급 검증이 아닙니다.",
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "projects"},
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
