#!/usr/bin/env python3
# This file defines data contracts only.
# It does not implement execution logic and is not sufficient to run the system.

"""Standalone decision trace reader.

This utility demonstrates how to parse and analyze decision traces
from multi-model orchestration systems. It has zero external dependencies
beyond the Python standard library.

Usage:
    python trace_reader.py trace_format_example.jsonl
    python trace_reader.py --stats trace_format_example.jsonl
"""

import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional


@dataclass
class DecisionTrace:
    """A single decision trace record."""

    trace_id: str
    run_id: str
    task_id: str
    created_at: datetime
    execution_mode: str
    sigma: float
    probe_answers: list[str]
    routing_reason: str
    models_invoked: list[str]
    winner_model: Optional[str]
    final_answer: str
    cost_usd: float
    latency_ms: int

    @classmethod
    def from_dict(cls, data: dict) -> "DecisionTrace":
        """Parse a trace from a dictionary."""
        return cls(
            trace_id=data["trace_id"],
            run_id=data["run_id"],
            task_id=data["task_id"],
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            execution_mode=data["execution_mode"],
            sigma=data["sigma"],
            probe_answers=data["probe_answers"],
            routing_reason=data["routing_reason"],
            models_invoked=data["models_invoked"],
            winner_model=data.get("winner_model"),
            final_answer=data["final_answer"],
            cost_usd=data["cost_usd"],
            latency_ms=data["latency_ms"],
        )


def read_traces(path: Path) -> Iterator[DecisionTrace]:
    """Read decision traces from a JSONL file.

    Args:
        path: Path to JSONL file

    Yields:
        DecisionTrace objects
    """
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                yield DecisionTrace.from_dict(data)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: Skipping invalid trace at line {line_num}: {e}", file=sys.stderr)


def compute_stats(traces: list[DecisionTrace]) -> dict:
    """Compute summary statistics from traces.

    Args:
        traces: List of decision traces

    Returns:
        Dictionary of statistics
    """
    if not traces:
        return {"error": "No traces provided"}

    mode_counts = Counter(t.execution_mode for t in traces)
    winner_counts = Counter(t.winner_model for t in traces if t.winner_model)
    total_cost = sum(t.cost_usd for t in traces)
    total_latency = sum(t.latency_ms for t in traces)

    return {
        "total_traces": len(traces),
        "execution_mode_distribution": dict(mode_counts),
        "winner_distribution": dict(winner_counts),
        "total_cost_usd": round(total_cost, 4),
        "avg_cost_usd": round(total_cost / len(traces), 4),
        "avg_latency_ms": round(total_latency / len(traces), 1),
        "sigma_distribution": {
            "0.0 (full agreement)": sum(1 for t in traces if t.sigma == 0.0),
            "0.5 (partial agreement)": sum(1 for t in traces if t.sigma == 0.5),
            "1.0 (full disagreement)": sum(1 for t in traces if t.sigma == 1.0),
        },
    }


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python trace_reader.py [--stats] <trace_file.jsonl>")
        sys.exit(1)

    show_stats = "--stats" in sys.argv
    file_args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not file_args:
        print("Error: No input file specified")
        sys.exit(1)

    path = Path(file_args[0])
    if not path.exists():
        print(f"Error: File not found: {path}")
        sys.exit(1)

    traces = list(read_traces(path))
    print(f"Read {len(traces)} traces from {path}")

    if show_stats:
        stats = compute_stats(traces)
        print("\n=== Summary Statistics ===")
        print(json.dumps(stats, indent=2))
    else:
        print("\n=== Traces ===")
        for trace in traces:
            print(f"  [{trace.execution_mode}] {trace.task_id}: sigma={trace.sigma}, "
                  f"cost=${trace.cost_usd:.4f}, latency={trace.latency_ms}ms")


if __name__ == "__main__":
    main()
