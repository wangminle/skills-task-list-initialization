#!/usr/bin/env python3
"""Aggregate real-agent eval runs into evals/benchmark.json (plan §7 D1 / REQ-09).

Reads every run.json under evals/workspace/runs/<config>/<run-dir>/ and emits the
benchmark summary the guard test (tests/scripts/test_evals_meta.py) validates:
no placeholders, no all-zero tokens/tool_calls, and runs_per_configuration equal to
the actual number of run directories per configuration. Values come from the real
claude-CLI transcripts — this script never invents metrics.
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
RUNS_ROOT = SKILL_DIR / "evals" / "workspace" / "runs"
BENCHMARK = SKILL_DIR / "evals" / "benchmark.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-per-configuration", type=int, default=3)
    args = parser.parse_args()

    configurations = []
    for config_dir in sorted(p for p in RUNS_ROOT.iterdir() if p.is_dir()):
        runs = []
        for run_dir in sorted(p for p in config_dir.iterdir() if p.is_dir()):
            record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            runs.append({
                "run_number": record["run_number"],
                "model": record["canonical_model"] or record["model"],
                "input_tokens": record["input_tokens"],
                "output_tokens": record["output_tokens"],
                # Guard reads flat tokens/tool_calls; keep the richer split too.
                "tokens": record["input_tokens"] + record["output_tokens"],
                "tool_calls": record["tool_calls"],
                "duration_s": record["duration_s"],
                "cost_usd": record["cost_usd"],
                "is_error": record["is_error"],
                "task_success": record.get("task_success"),
                "workspace": record["workspace"],
            })
        configurations.append({
            "name": config_dir.name,
            "runs": runs,
            "task_success_rate": (
                sum(1 for r in runs if r.get("task_success")) / len(runs) if runs else 0
            ),
            "median_duration_s": statistics.median(r["duration_s"] for r in runs),
        })

    if not configurations:
        raise SystemExit("no run directories found under evals/workspace/runs/")
    benchmark = {
        "skill_name": "task-list-initialization",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "runs_per_configuration": args.runs_per_configuration,
        "harness": "claude-cli headless (-p --output-format stream-json)",
        "configurations": configurations,
    }
    BENCHMARK.write_text(
        json.dumps(benchmark, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    total = sum(len(c["runs"]) for c in configurations)
    print(f"wrote {BENCHMARK} ({len(configurations)} configurations, {total} runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
