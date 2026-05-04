#!/usr/bin/env python3
import argparse
import json
import os
import signal
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path


BASE_LAYOUT = "go,c-lean,rust,go,rust,go,c-lean,c-lean,rust"
NODE_COUNT = 9
DEFAULT_TIMEOUT_SEC = 300


@dataclass
class Result:
    name: str
    layout: str
    status: str
    output_dir: str
    duration_sec: float


def swapped_layout(index: int, replacement: str) -> str:
    entries = BASE_LAYOUT.split(",")
    if index < 0 or index >= len(entries):
        raise ValueError("swap index outside 9-node layout")
    entries[index] = replacement
    return ",".join(entries)


def render_markdown(results: list[Result]) -> str:
    lines = [
        "## GossipSub side-by-side results",
        "",
        "| Name | Status | Duration | Output | Layout |",
        "|---|---|---:|---|---|",
    ]
    for result in results:
        lines.append(
            f"| {result.name} | {result.status.upper()} | "
            f"{result.duration_sec:.1f}s | {result.output_dir} | `{result.layout}` |"
        )
    lines.append("")
    return "\n".join(lines)


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


def prepare_c_lean_identities(output_root: Path) -> None:
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
        str(NODE_COUNT),
    ]
    print(
        f"[gossipsub-side-by-side] prepare c-lean identities dir={identity_dir}",
        flush=True,
    )
    subprocess.run(cmd, check=True)
    os.environ["C_LEAN_LIBP2P_GOSSIPSUB_IDENTITY_DIR"] = str(identity_dir)


def run_layout(
    name: str,
    layout: str,
    output_root: Path,
    scenario: str,
    seed: int,
    timeout_sec: int,
) -> Result:
    output_dir = output_root / name
    cmd = [
        "uv",
        "run",
        "run.py",
        "--node_count",
        str(NODE_COUNT),
        "--composition",
        "c-lean-rust-go",
        "--scenario",
        scenario,
        "--seed",
        str(seed),
        "--binary_layout",
        layout,
        "--output_dir",
        str(output_dir),
    ]
    env = os.environ.copy()
    env["GOSSIPSUB_INTEROP_SKIP_BUILD"] = env.get("GOSSIPSUB_INTEROP_SKIP_BUILD", "1")
    print(
        f"[gossipsub-side-by-side] start name={name} scenario={scenario} "
        f"seed={seed} layout={layout}",
        flush=True,
    )
    started = time.monotonic()
    run_status = run_with_timeout(cmd, env, timeout_sec)
    duration = time.monotonic() - started
    if run_status == 124:
        status = "timeout"
    elif run_status != 0:
        status = "fail"
    else:
        status = "pass"
    print(
        f"[gossipsub-side-by-side] done name={name} "
        f"status={status} duration={duration:.1f}s",
        flush=True,
    )
    return Result(name, layout, status, str(output_dir), duration)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--scenario", default="subnet-blob-msg")
    parser.add_argument("--seed", type=int, default=2)
    parser.add_argument("--swap-index", type=int, default=7)
    parser.add_argument("--replacement", choices=["go", "rust"], default="go")
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    args = parser.parse_args()

    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    prepare_c_lean_identities(output_root)

    results = [
        run_layout(
            "base",
            BASE_LAYOUT,
            output_root,
            args.scenario,
            args.seed,
            args.timeout_sec,
        )
    ]
    results.append(
        run_layout(
            f"swap-node{args.swap_index}-{args.replacement}",
            swapped_layout(args.swap_index, args.replacement),
            output_root,
            args.scenario,
            args.seed,
            args.timeout_sec,
        )
    )

    (output_root / "results.json").write_text(
        json.dumps([asdict(result) for result in results], indent=2) + "\n"
    )
    matrix = render_markdown(results)
    (output_root / "matrix.md").write_text(matrix)
    print(matrix)
    return 1 if any(result.status == "timeout" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
