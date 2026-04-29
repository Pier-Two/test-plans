#!/usr/bin/env python3
import argparse
import json
import os
import random
import subprocess
from dataclasses import asdict

import experiment
from analyze_message_deliveries import analyse_message_deliveries
from network_graph import generate_graph

params_file_name = "params.json"


def choose_binary_paths(binaries, node_count):
    total_weight = sum(b.percent_of_nodes for b in binaries)
    counts = []
    assigned = 0
    for binary in binaries:
        count = (node_count * binary.percent_of_nodes) // total_weight
        counts.append(count)
        assigned += count

    remainders = sorted(
        range(len(binaries)),
        key=lambda i: (node_count * binaries[i].percent_of_nodes) % total_weight,
        reverse=True,
    )
    for i in remainders[: node_count - assigned]:
        counts[i] += 1

    if node_count >= len(binaries):
        for i, count in enumerate(counts):
            if count == 0:
                donor = max(range(len(counts)), key=lambda j: counts[j])
                counts[donor] -= 1
                counts[i] = 1

    binary_paths = []
    for binary, count in zip(binaries, counts):
        binary_paths.extend([binary.path] * count)
    random.shuffle(binary_paths)
    return binary_paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        type=bool,
        required=False,
        help="If set, will generate files but not run Shadow",
        default=False,
    )
    parser.add_argument("--node_count", type=int, required=True)
    parser.add_argument("--disable_gossip", type=bool, required=False)
    parser.add_argument("--seed", type=int, required=False, default=1)
    parser.add_argument(
        "--scenario", type=str, required=False, default="subnet-blob-msg"
    )
    parser.add_argument("--composition", type=str, required=False, default="all-go")
    parser.add_argument("--output_dir", type=str, required=False)
    args = parser.parse_args()

    shadow_outputs_dir = os.path.join(os.getcwd(), "shadow-outputs")
    os.makedirs(shadow_outputs_dir, exist_ok=True)

    if args.output_dir is None:
        try:
            git_describe = (
                subprocess.check_output(["git", "describe", "--always", "--dirty"])
                .decode("utf-8")
                .strip()
            )
        except subprocess.CalledProcessError:
            git_describe = "unknown"

        import datetime

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        args.output_dir = (
            f"{args.scenario}-{args.node_count}-{args.composition}-"
            f"{args.seed}-{timestamp}-{git_describe}.data"
        )

    if not os.path.isabs(args.output_dir):
        args.output_dir = os.path.join(shadow_outputs_dir, args.output_dir)

    random.seed(args.seed)

    binaries = experiment.composition(args.composition)
    experiment_params = experiment.scenario(
        args.scenario, args.node_count, args.disable_gossip
    )

    with open(params_file_name, "w") as f:
        d = asdict(experiment_params)
        d["script"] = [
            instruction.model_dump(exclude_none=True)
            for instruction in experiment_params.script
        ]
        json.dump(d, f)

    # Define the binaries we are running
    binary_paths = choose_binary_paths(binaries, args.node_count)

    # Generate the network graph and the Shadow config for the binaries
    generate_graph(
        binary_paths,
        "graph.gml",
        "shadow.yaml",
        params_file_location=os.path.join(os.getcwd(), params_file_name),
    )

    if args.dry_run:
        return

    if os.environ.get("GOSSIPSUB_INTEROP_SKIP_BUILD") != "1":
        subprocess.run(["make", "binaries"], check=True)

    subprocess.run(
        ["shadow", "--progress", "true", "-d", args.output_dir, "shadow.yaml"],
        check=True,
    )

    # Move files to output_dir
    os.rename("shadow.yaml", os.path.join(args.output_dir, "shadow.yaml"))
    os.rename("graph.gml", os.path.join(args.output_dir, "graph.gml"))
    os.rename("params.json", os.path.join(args.output_dir, "params.json"))

    link_name = "latest"
    if os.path.islink(link_name) or os.path.exists(link_name):
        os.remove(link_name)
    os.symlink(args.output_dir, link_name)

    # Analyse message deliveries. Skip the first 4 as warmup messages
    analyse_message_deliveries(args.output_dir, f"{args.output_dir}/plots", 4)


if __name__ == "__main__":
    main()
