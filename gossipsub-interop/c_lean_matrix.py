#!/usr/bin/env python3
import argparse
import json
import os
import signal
import subprocess
import time
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
    timeout_sec: int = 300


@dataclass
class Result:
    pair: str
    composition: str
    scenario: str
    status: str
    output_dir: str
    duration_sec: float


def run_with_timeout(cmd: list[str], env: dict[str, str], timeout_sec: int) -> int:
    proc = subprocess.Popen(cmd, env=env, start_new_session=True)
    try:
        return proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return proc.wait()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                return proc.wait()
            proc.wait()
        return 124


def prepare_c_lean_identities(cases: list[Case], output_root: Path) -> None:
    runnable_cases = [case for case in cases if not case.unsupported]
    if not runnable_cases:
        return
    max_nodes = max(case.node_count for case in runnable_cases)
    identity_dir = output_root / "c-lean-identities"
    binary = os.environ.get(
        "C_LEAN_LIBP2P_GOSSIPSUB_BIN",
        "/workspace/build-gossipsub-interop/bin/c_lean_libp2p_gossipsub_interop",
    )
    cmd = [
        binary,
        "--write-identities",
        str(identity_dir),
        "--node-count",
        str(max_nodes),
    ]
    print(
        f"[gossipsub-matrix] prepare c-lean identities dir={identity_dir} nodes={max_nodes}",
        flush=True,
    )
    subprocess.run(cmd, check=True)
    os.environ["C_LEAN_LIBP2P_GOSSIPSUB_IDENTITY_DIR"] = str(identity_dir)


def run_case(case: Case, output_root: Path) -> Result:
    output_dir = output_root / f"{case.scenario}-{case.composition}-seed{case.seed}"
    if case.unsupported:
        return Result(
            pair=case.pair,
            composition=case.composition,
            scenario=case.scenario,
            status="unsupported",
            output_dir="n/a",
            duration_sec=0.0,
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
    started = time.monotonic()
    print(
        f"[gossipsub-matrix] start pair={case.pair} scenario={case.scenario} "
        f"composition={case.composition} nodes={case.node_count} seed={case.seed}",
        flush=True,
    )
    run_status = run_with_timeout(cmd, env, case.timeout_sec)
    if run_status == 124:
        status = "timeout"
    elif run_status != 0:
        status = "fail"
    elif case.partial_count is not None:
        check_status = run_with_timeout(
            [
                "uv",
                "run",
                "checks/partial_messages.py",
                str(output_dir),
                "--count",
                str(case.partial_count),
            ],
            env,
            case.timeout_sec,
        )
        if check_status == 124:
            status = "timeout"
        elif check_status != 0:
            status = "fail"

    duration = time.monotonic() - started
    print(
        f"[gossipsub-matrix] done pair={case.pair} scenario={case.scenario} "
        f"status={status} duration={duration:.1f}s",
        flush=True,
    )

    return Result(
        pair=case.pair,
        composition=case.composition,
        scenario=case.scenario,
        status=status,
        output_dir=str(output_dir),
        duration_sec=duration,
    )


def render_markdown(results: list[Result]) -> str:
    lines = [
        "## GossipSub interop results",
        "",
        "Advisory run: FAIL rows are reported here and in the artifact; TIMEOUT rows fail the job.",
        "",
        "| Pair | Scenario | Composition | Status | Duration | Output |",
        "|---|---|---|---|---:|---|",
    ]
    for result in results:
        label = result.status.upper()
        lines.append(
            f"| {result.pair} | {result.scenario} | {result.composition} | "
            f"{label} | {result.duration_sec:.1f}s | {result.output_dir} |"
        )
    lines.append("")
    return "\n".join(lines)


def filter_cases(cases: list[Case], pair: str, scenario: str) -> list[Case]:
    selected = []
    for case in cases:
        pair_match = pair == "all" or case.pair == pair or case.composition == pair
        scenario_match = scenario == "all" or case.scenario == scenario
        if pair_match and scenario_match:
            selected.append(case)
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True)
    parser.add_argument(
        "--pair", default=os.environ.get("GOSSIPSUB_INTEROP_PAIR", "all")
    )
    parser.add_argument(
        "--scenario", default=os.environ.get("GOSSIPSUB_INTEROP_SCENARIO", "all")
    )
    args = parser.parse_args()

    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    cases = [
        Case("c-lean-libp2p/go-libp2p", "c-lean-and-go", "subnet-blob-msg", 8, 1),
        Case("c-lean-libp2p/go-libp2p", "c-lean-and-go", "simple-fanout", 8, 1),
        Case("c-lean-libp2p/rust-libp2p", "c-lean-and-rust", "subnet-blob-msg", 8, 1),
        Case("c-lean-libp2p/rust-libp2p", "c-lean-and-rust", "simple-fanout", 8, 1),
        Case("c-lean-libp2p/go-libp2p/rust-libp2p", "c-lean-rust-go", "subnet-blob-msg", 32, 2),
        Case(
            "c-lean-libp2p/go-libp2p",
            "not-run",
            "partial-messages",
            0,
            0,
            unsupported=True,
        ),
        Case(
            "c-lean-libp2p/go-libp2p",
            "not-run",
            "partial-messages-chain",
            0,
            0,
            unsupported=True,
        ),
        Case(
            "c-lean-libp2p/go-libp2p",
            "not-run",
            "partial-messages-fanout",
            0,
            0,
            unsupported=True,
        ),
        Case(
            "c-lean-libp2p/rust-libp2p",
            "not-run",
            "partial-messages",
            0,
            0,
            unsupported=True,
        ),
        Case(
            "c-lean-libp2p/rust-libp2p",
            "not-run",
            "partial-messages-chain",
            0,
            0,
            unsupported=True,
        ),
        Case(
            "c-lean-libp2p/rust-libp2p",
            "not-run",
            "partial-messages-fanout",
            0,
            0,
            unsupported=True,
        ),
    ]
    cases = filter_cases(cases, args.pair, args.scenario)
    if not cases:
        raise SystemExit(
            f"no gossipsub interop cases match pair={args.pair} scenario={args.scenario}"
        )

    prepare_c_lean_identities(cases, output_root)

    results = []
    for case in cases:
        results.append(run_case(case, output_root))
        (output_root / "results.json").write_text(
            json.dumps([asdict(result) for result in results], indent=2) + "\n"
        )
        (output_root / "matrix.md").write_text(render_markdown(results))
    (output_root / "results.json").write_text(
        json.dumps([asdict(result) for result in results], indent=2) + "\n"
    )
    matrix = render_markdown(results)
    (output_root / "matrix.md").write_text(matrix)
    print(matrix)
    return 1 if any(result.status == "timeout" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
