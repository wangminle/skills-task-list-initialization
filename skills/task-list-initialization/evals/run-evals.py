#!/usr/bin/env python3
"""REQ-09 real-agent evaluation runner (plan §7 D1).

Runs evals.json prompts against a REAL agent (claude CLI headless mode) in isolated
workspaces, two configurations per evaluation:

  with_skill — the working-tree skill is installed into the workspace
               (.claude/skills/task-list-initialization), so discovery is guaranteed
               and the benchmark measures the CURRENT code;
  baseline   — no skill anywhere (the user-scope install must be moved aside first;
               the runner refuses to start if it is still present).

Each run records REAL telemetry from the CLI transcript: model name (modelUsage),
input/output tokens, tool_use event count, wall duration, and cost. Transcripts are
kept under evals/workspace/runs/<config>/<run-dir>/ so the aggregator (and the
benchmark guard test) can verify declared counts against actual directories.

Usage:
  python3 evals/run-evals.py --evals 1,3,5 --runs 3
  python3 evals/aggregate-benchmark.py --runs-per-configuration 3

Environment requirement: the harness CLI must actually surface file-write tools to
the agent. On the 2026-08-17 first batch the local CLI's dynamic tool discovery
(ToolSearch) failed to surface Write even though it appeared in the init tool list,
so no run — either configuration — could create or edit task-list.md; that batch was
discarded (output review, plan D1 step 7) rather than benchmarked. Re-run after the
harness makes Write reachable; each run's task_success (file created/changed) is
recorded so a silently-blocked batch is visible in the aggregate, not just tokens.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent          # skills/task-list-initialization
REPO_ROOT = SKILL_DIR.parent.parent                          # repo root
EVALS_JSON = SKILL_DIR / "evals" / "evals.json"
FIXTURES = SKILL_DIR / "evals"
RUNS_ROOT = SKILL_DIR / "evals" / "workspace" / "runs"
USER_SCOPE_SKILL = Path.home() / ".claude" / "skills" / "task-list-initialization"
USER_SCOPE_PARKED = Path.home() / ".claude" / "skills" / ".task-list-initialization.eval-parked"
RUN_TIMEOUT_S = 300


def load_evals(ids: list[int]) -> list[dict]:
    data = json.loads(EVALS_JSON.read_text(encoding="utf-8"))
    return [e for e in data["evals"] if e["id"] in ids]


def prepare_workspace(root: Path, eval_: dict, with_skill: bool) -> str | None:
    """Set up the workspace; return the original text of task-list.md (if any) so
    per-run outcome validation can tell "agent changed it" from "agent only read"."""
    root.mkdir(parents=True, exist_ok=True)
    original = None
    files = eval_.get("files", [])
    for index, rel in enumerate(files):
        src = SKILL_DIR / rel
        # Prompts reference task-list.md at the project root — the (single) fixture
        # must materialize there even when its repo name differs (eval3 first-batch bug).
        dst = root / "task-list.md" if index == 0 and len(files) == 1 else root / src.name
        if dst.name == "task-list.md":
            original = src.read_text(encoding="utf-8")
        shutil.copyfile(src, dst)
    if with_skill:
        dest = root / ".claude" / "skills" / "task-list-initialization"
        shutil.copytree(
            SKILL_DIR, dest,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "evals", ".DS_Store"),
        )
    # Tool-deferral isolation: user-scope ENABLE_TOOL_SEARCH=true hides Write/Bash
    # behind ToolSearch, which headless agents often fail to discover (every run
    # TASK-FAILs while only calling ToolSearch). Disable it per workspace so both
    # configurations see the classic always-available tool set, matching the
    # environment the original successful run benchmarked. Workspace settings
    # override the user scope; nothing global is touched.
    settings = root / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text('{"env": {"ENABLE_TOOL_SEARCH": "false"}}\n', encoding="utf-8")


def run_once(config: str, eval_: dict, run_number: int) -> dict:
    workdir = RUNS_ROOT / config / f"eval{eval_['id']}-run{run_number}"
    if workdir.exists():
        shutil.rmtree(workdir)
    original = prepare_workspace(workdir, eval_, with_skill=config.endswith("with_skill"))

    started = time.monotonic()
    proc = subprocess.run(
        ["claude", "-p", eval_["prompt"],
         "--verbose", "--output-format", "stream-json",
         "--dangerously-skip-permissions"],
        cwd=str(workdir), capture_output=True, text=True, timeout=RUN_TIMEOUT_S,
    )
    duration_s = round(time.monotonic() - started, 1)
    (workdir / "transcript.jsonl").write_text(proc.stdout, encoding="utf-8")
    (workdir / "stderr.txt").write_text(proc.stderr, encoding="utf-8")

    tool_calls = 0
    result: dict = {}
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "assistant":
            for item in event.get("message", {}).get("content", []):
                if isinstance(item, dict) and item.get("type") == "tool_use":
                    tool_calls += 1
        if event.get("type") == "result":
            result = event

    usage = result.get("usage", {}) or {}
    model_usage = result.get("modelUsage", {}) or {}
    model = next(iter(model_usage), None) or "unknown"
    record = {
        "run_number": run_number,
        "eval_id": eval_["id"],
        "eval_name": eval_["name"],
        "configuration": config,
        "model": model,
        "canonical_model": model_usage.get(model, {}).get("canonicalModel", model),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "tool_calls": tool_calls,
        "num_turns": result.get("num_turns"),
        "duration_s": duration_s,
        "cost_usd": result.get("total_cost_usd"),
        "is_error": result.get("is_error", proc.returncode != 0),
        "workspace": str(workdir.relative_to(REPO_ROOT)),
    }
    # Outcome validation: did the agent actually do the task? With a pre-existing
    # task-list.md the file must have changed; without one (init evals) it must exist.
    ledger = workdir / "task-list.md"
    if original is None:
        task_success = ledger.exists()
    else:
        task_success = ledger.exists() and ledger.read_text(encoding="utf-8") != original
    record["task_success"] = task_success

    (workdir / "run.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evals", default="1,3,5", help="comma-separated eval ids")
    parser.add_argument("--runs", type=int, default=3, help="runs per eval x config")
    args = parser.parse_args()
    ids = [int(x) for x in args.evals.split(",") if x.strip()]
    evals = load_evals(ids)
    if not evals:
        print(f"no evals found for ids {ids}", file=sys.stderr)
        return 2

    # A true baseline requires the skill to be undiscoverable everywhere. Refuse to
    # run (rather than silently contaminate) if the user-scope install is present.
    if USER_SCOPE_SKILL.exists():
        print(
            f"refusing: {USER_SCOPE_SKILL} is installed user-scope and would "
            f"contaminate baseline runs. Park it first:\n"
            f"  mv '{USER_SCOPE_SKILL}' '{USER_SCOPE_PARKED}'",
            file=sys.stderr,
        )
        return 3

    for eval_ in evals:
        for config in (f"eval{eval_['id']}-with_skill", f"eval{eval_['id']}-baseline"):
            for run_number in range(1, args.runs + 1):
                record = run_once(config, eval_, run_number)
                status = ("ERR" if record["is_error"] else "ok") + ("" if record["task_success"] else "/TASK-FAIL")
                print(
                    f"[{status}] {config} run{run_number}: model={record['model']} "
                    f"in={record['input_tokens']} out={record['output_tokens']} "
                    f"tools={record['tool_calls']} {record['duration_s']}s "
                    f"${record['cost_usd']}",
                    flush=True,
                )
    print("all runs complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
