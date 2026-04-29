#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class Case:
    pair: str
    composition: str
    scenario: str
    node_count: int
    seed: int
    partial_count: Optional[int] = None
    unsupported: bool = False


@dataclass
class Result:
    pair: str
    composition: str
    scenario: str
    status: str
    output_dir: str


def run_case(case: Case, output_root: Path) -> Result:
    output_dir = output_root / f"{case.scenario}-{case.composition}-seed{case.seed}"
    if case.unsupported:
        return Result(
            pair=case.pair,
            composition=case.composition,
            scenario=case.scenario,
            status="unsupported",
            output_dir="n/a",
        )

    env = os.environ.copy()
    env["GOSSIPSUB_INTEROP_SKIP_BUILD"] = "1"
    cmd = [
        "uv",
        "run",
        "run.py",
        "--node_count",
        str(case.node_count),
        "--composition",
        case.composition,
        "--scenario",
        case.scenario,
        "--seed",
        str(case.seed),
        "--output_dir",
        str(output_dir),
    ]
    status = "pass"
    try:
        subprocess.run(cmd, check=True, env=env)
        if case.partial_count is not None:
            subprocess.run(
                [
                    "uv",
                    "run",
                    "checks/partial_messages.py",
                    str(output_dir),
                    "--count",
                    str(case.partial_count),
                ],
                check=True,
                env=env,
            )
    except subprocess.CalledProcessError:
        status = "fail"

    return Result(
        pair=case.pair,
        composition=case.composition,
        scenario=case.scenario,
        status=status,
        output_dir=str(output_dir),
    )


def render_markdown(results: list[Result]) -> str:
    lines = [
        "## GossipSub interop results",
        "",
        "| Pair | Scenario | Composition | Status | Output |",
        "|---|---|---|---|---|",
    ]
    for result in results:
        label = result.status.upper()
        lines.append(
            f"| {result.pair} | {result.scenario} | {result.composition} | "
            f"{label} | {result.output_dir} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()

    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    cases = [
        Case("c-lean-libp2p/go-libp2p", "c-lean-and-go", "subnet-blob-msg", 8, 1),
        Case("c-lean-libp2p/go-libp2p", "c-lean-and-go", "simple-fanout", 8, 1),
        Case("c-lean-libp2p/rust-libp2p", "c-lean-and-rust", "subnet-blob-msg", 8, 1),
        Case("c-lean-libp2p/rust-libp2p", "c-lean-and-rust", "simple-fanout", 8, 1),
        Case("c-lean-libp2p/go-libp2p/rust-libp2p", "c-lean-rust-go", "subnet-blob-msg", 9, 2),
        Case("go-libp2p/rust-libp2p", "rust-and-go", "partial-messages", 8, 1, partial_count=1),
        Case("go-libp2p/rust-libp2p", "rust-and-go", "partial-messages-chain", 8, 1, partial_count=16),
        Case("go-libp2p/rust-libp2p", "rust-and-go", "partial-messages-fanout", 8, 1, partial_count=1),
        Case(
            "c-lean-libp2p/*",
            "not-run",
            "partial-messages",
            0,
            0,
            unsupported=True,
        ),
        Case(
            "c-lean-libp2p/*",
            "not-run",
            "partial-messages-chain",
            0,
            0,
            unsupported=True,
        ),
        Case(
            "c-lean-libp2p/*",
            "not-run",
            "partial-messages-fanout",
            0,
            0,
            unsupported=True,
        ),
    ]

    results = [run_case(case, output_root) for case in cases]
    (output_root / "results.json").write_text(
        json.dumps([asdict(result) for result in results], indent=2) + "\n"
    )
    matrix = render_markdown(results)
    (output_root / "matrix.md").write_text(matrix)
    print(matrix)
    return 1 if any(result.status == "fail" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
