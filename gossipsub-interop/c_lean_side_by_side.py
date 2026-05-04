#!/usr/bin/env python3
import argparse
import os
import subprocess
from pathlib import Path


BASE_LAYOUT = "go,c-lean,rust,go,rust,go,c-lean,c-lean,rust"


def swapped_layout(index: int, replacement: str) -> str:
    entries = BASE_LAYOUT.split(",")
    if index < 0 or index >= len(entries):
        raise ValueError("swap index outside 9-node layout")
    entries[index] = replacement
    return ",".join(entries)


def run_layout(name: str, layout: str, output_root: Path, scenario: str, seed: int) -> None:
    output_dir = output_root / name
    cmd = [
        "uv",
        "run",
        "run.py",
        "--node_count",
        "9",
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
    subprocess.run(cmd, check=True, env=env)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--scenario", default="subnet-blob-msg")
    parser.add_argument("--seed", type=int, default=2)
    parser.add_argument("--swap-index", type=int, default=7)
    parser.add_argument("--replacement", choices=["go", "rust"], default="go")
    args = parser.parse_args()

    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    run_layout("base", BASE_LAYOUT, output_root, args.scenario, args.seed)
    run_layout(
        f"swap-node{args.swap_index}-{args.replacement}",
        swapped_layout(args.swap_index, args.replacement),
        output_root,
        args.scenario,
        args.seed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
