#!/usr/bin/env python3
"""Inspect processed SEC-bench data and matching Docker repositories."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any


DEFAULT_HF_HOME = Path(".cache/huggingface")


EXECUTION_PATH_PROFILES: dict[str, list[tuple[str, str]]] = {
    "wasm3.ossfuzz-42496369": [
        (
            "CLI loading and function dispatch",
            'nl -ba platforms/app/main.c | sed -n "104,156p;238,276p;533,607p"',
        ),
        (
            "Function lookup and lazy compilation",
            'nl -ba source/m3_env.c | sed -n "670,704p"',
        ),
        (
            "Wasm parser constraints",
            'nl -ba source/m3_parse.c | sed -n "47,95p;126,140p;225,242p;323,371p"',
        ),
        (
            "Compilation and extended opcode dispatch",
            'nl -ba source/m3_compile.c | sed -n "1105,1124p;2388,2446p;2453,2480p;2698,2768p"',
        ),
        (
            "Operation metadata structure",
            'nl -ba source/m3_compile.h | sed -n "118,158p"',
        ),
    ],
    "njs.cve-2022-32414": [
        (
            "Promise.race implementation and handler",
            'nl -ba src/njs_promise.c | sed -n "1688,1765p"',
        ),
        (
            "Iterator value production",
            'nl -ba src/njs_iterator.c | sed -n "299,390p"',
        ),
        (
            "Async await continuation",
            'nl -ba src/njs_async.c | sed -n "58,108p"',
        ),
        (
            "VM await setup and property-next crash point",
            'nl -ba src/njs_vmcode.c | sed -n "796,810p;1940,1964p"',
        ),
    ],
}


SUMMARY_FIELDS = [
    "instance_id",
    "repo",
    "project_name",
    "lang",
    "work_dir",
    "sanitizer",
    "bug_description",
    "base_commit",
    "exit_code",
]


LONG_TEXT_FIELDS = [
    "sanitizer_report",
    "bug_report",
    "secb_sh",
    "build_sh",
    "dockerfile",
    "patch",
]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for dataset and Docker inspection."""
    parser = argparse.ArgumentParser(
        description="Load a SEC-bench dataset item and inspect its Docker repo."
    )
    parser.add_argument(
        "--config",
        default="config.toml",
        help="Path to the SEC-bench config file.",
    )
    parser.add_argument(
        "--dataset",
        help="Dataset name. Defaults to [dataset].name from config.",
    )
    parser.add_argument(
        "--split",
        help="Dataset split. Defaults to [dataset].split from config.",
    )
    parser.add_argument(
        "--instance-id",
        help="Instance ID to inspect. If omitted, --row-index is used.",
    )
    parser.add_argument(
        "--row-index",
        type=int,
        default=0,
        help="Dataset row index to inspect when --instance-id is omitted.",
    )
    parser.add_argument(
        "--task-tag",
        choices=["auto", "poc", "patch", "latest"],
        default="auto",
        help="Docker image tag to inspect.",
    )
    parser.add_argument(
        "--image-prefix",
        help="Docker image prefix. Defaults to [docker].image_prefix from config.",
    )
    parser.add_argument(
        "--hf-home",
        default=str(DEFAULT_HF_HOME),
        help="Hugging Face cache directory.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use only local Hugging Face cache.",
    )
    parser.add_argument(
        "--skip-docker",
        action="store_true",
        help="Only inspect the dataset item, not the Docker image.",
    )
    parser.add_argument(
        "--skip-path",
        action="store_true",
        help="Skip profiled execution-path source snippets.",
    )
    parser.add_argument(
        "--full-text",
        action="store_true",
        help="Print complete long text fields instead of previews.",
    )
    return parser.parse_args()


def load_config(config_path: Path) -> dict[str, Any]:
    """Load a TOML configuration file."""
    with config_path.open("rb") as config_file:
        return tomllib.load(config_file)


def configure_huggingface_cache(hf_home: Path, offline: bool) -> None:
    """Configure Hugging Face cache and offline environment variables."""
    os.environ.setdefault("HF_HOME", str(hf_home.resolve()))
    if offline:
        os.environ["HF_DATASETS_OFFLINE"] = "1"
        os.environ["HF_HUB_OFFLINE"] = "1"


def load_dataset_split(dataset_name: str, split: str) -> Any:
    """Load a single split from the SEC-bench dataset."""
    from datasets import load_dataset

    return load_dataset(dataset_name, split=split)


def load_all_splits(dataset_name: str) -> Any:
    """Load all available splits from the SEC-bench dataset."""
    from datasets import DatasetDict, load_dataset

    loaded = load_dataset(dataset_name)
    if not isinstance(loaded, DatasetDict):
        raise TypeError(f"Expected DatasetDict for {dataset_name}, got {type(loaded)}")
    return loaded


def select_row(dataset: Any, instance_id: str | None, row_index: int) -> dict[str, Any]:
    """Select a dataset row by instance ID or row index."""
    if instance_id:
        for row in dataset:
            if row.get("instance_id") == instance_id:
                return dict(row)
        raise ValueError(f"Instance ID not found in split: {instance_id}")

    if row_index < 0 or row_index >= len(dataset):
        raise IndexError(f"Row index {row_index} is outside dataset size {len(dataset)}")

    return dict(dataset[row_index])


def resolve_task_tag(config: dict[str, Any], requested_tag: str) -> str:
    """Resolve the Docker image tag from config and command-line arguments."""
    if requested_tag != "auto":
        return requested_tag

    task_type = config.get("task", {}).get("type", "poc-repo")
    if task_type == "patch":
        return "patch"

    return "poc"


def resolve_image_name(
    config: dict[str, Any],
    row: dict[str, Any],
    requested_prefix: str | None,
    tag: str,
) -> str:
    """Resolve the Docker image name for an instance row."""
    image_prefix = requested_prefix or config.get("docker", {}).get(
        "image_prefix", "hwiwonlee/secb.eval.x86_64"
    )
    return f"{image_prefix}.{row['instance_id']}:{tag}"


def preview_text(value: Any, max_chars: int = 800) -> Any:
    """Return a compact preview for long string values."""
    if not isinstance(value, str):
        return value
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + f"\n... <truncated {len(value) - max_chars} chars>"


def print_json_heading(title: str, payload: Any) -> None:
    """Print a titled JSON payload."""
    print(f"\n=== {title} ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def summarize_dataset(dataset_name: str) -> dict[str, Any]:
    """Return split sizes for a dataset when all splits can be loaded."""
    try:
        splits = load_all_splits(dataset_name)
    except Exception as exc:
        return {"error": -1, "detail": str(exc)}
    return {split_name: len(split) for split_name, split in splits.items()}


def build_row_summary(row: dict[str, Any], full_text: bool) -> dict[str, Any]:
    """Build a printable summary for a SEC-bench row."""
    summary: dict[str, Any] = {field: row.get(field) for field in SUMMARY_FIELDS}
    for field in LONG_TEXT_FIELDS:
        if field in row:
            summary[field] = row[field] if full_text else preview_text(row[field])
    return summary


def run_command(
    args: list[str],
    timeout_seconds: int = 120,
) -> subprocess.CompletedProcess[str]:
    """Run a local command and capture text output."""
    return subprocess.run(
        args,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_seconds,
    )


def docker_bash(image: str, command: str, timeout_seconds: int = 120) -> str:
    """Run a bash command inside a Docker image and return combined output."""
    result = run_command(
        ["docker", "run", "--rm", "--entrypoint", "bash", image, "-lc", command],
        timeout_seconds=timeout_seconds,
    )
    output = result.stdout
    if result.stderr:
        output += result.stderr
    if result.returncode != 0:
        output += f"\n<docker command exited with code {result.returncode}>"
    return output


def docker_image_info(image: str) -> dict[str, Any]:
    """Inspect the Docker image working directory and environment."""
    result = run_command(
        [
            "docker",
            "image",
            "inspect",
            image,
            "--format",
            "{{json .Config.WorkingDir}} {{json .Config.Env}}",
        ]
    )
    if result.returncode != 0:
        return {"error": result.stderr.strip() or result.stdout.strip()}
    return {"raw": result.stdout.strip()}


def inspect_container_basics(image: str, work_dir: str) -> dict[str, str]:
    """Read basic repository and SEC-bench helper information from a container."""
    command = (
        f"cd {shell_quote(work_dir)} && "
        "printf 'PWD: '; pwd && "
        "printf 'HEAD: '; git rev-parse HEAD 2>/dev/null || true && "
        "printf '\\n--- /usr/local/bin/secb ---\\n' && "
        "sed -n '1,260p' /usr/local/bin/secb"
    )
    return {"output": docker_bash(image, command)}


def shell_quote(value: str) -> str:
    """Quote a string for simple POSIX shell usage."""
    return "'" + value.replace("'", "'\"'\"'") + "'"


def inspect_execution_path(image: str, row: dict[str, Any]) -> dict[str, str]:
    """Read known execution-path source snippets for an instance."""
    instance_id = row["instance_id"]
    work_dir = row["work_dir"]
    snippets = EXECUTION_PATH_PROFILES.get(instance_id)
    if not snippets:
        return {
            "note": (
                f"No built-in execution-path profile for {instance_id}. "
                "Add commands to EXECUTION_PATH_PROFILES in this script."
            )
        }

    outputs: dict[str, str] = {}
    for title, snippet_command in snippets:
        command = f"cd {shell_quote(work_dir)} && {snippet_command}"
        outputs[title] = docker_bash(image, command)
    return outputs


def main() -> int:
    """Run dataset loading and Docker repository inspection."""
    args = parse_args()
    config_path = Path(args.config)
    config = load_config(config_path)

    hf_home = Path(args.hf_home)
    configure_huggingface_cache(hf_home, args.offline)

    dataset_name = args.dataset or config.get("dataset", {}).get(
        "name", "SEC-bench/SEC-bench"
    )
    split = args.split or config.get("dataset", {}).get("split", "eval")

    print_json_heading("Dataset Splits", summarize_dataset(dataset_name))

    dataset = load_dataset_split(dataset_name, split)
    row = select_row(dataset, args.instance_id, args.row_index)
    print_json_heading("Selected Row", build_row_summary(row, args.full_text))

    tag = resolve_task_tag(config, args.task_tag)
    image = resolve_image_name(config, row, args.image_prefix, tag)
    print_json_heading("Docker Image", {"image": image, "tag": tag})

    if args.skip_docker:
        return 0

    print_json_heading("Docker Image Inspect", docker_image_info(image))
    print_json_heading(
        "Container Repo And secb Helper",
        inspect_container_basics(image, row["work_dir"]),
    )

    if not args.skip_path:
        print_json_heading(
            "Execution Path Source Snippets",
            inspect_execution_path(image, row),
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
