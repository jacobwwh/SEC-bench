# SEC-bench Data And Repo Inspection

This directory contains small utilities for loading the processed SEC-bench dataset and inspecting the corresponding Docker evaluation repository.

## Inspect A Dataset Item

Use an activated `secb` conda environment:

```bash
conda activate secb
python read_data/inspect_instance.py \
  --config config.toml \
  --row-index 0 \
  --offline
```

Inspect a specific instance:

```bash
python read_data/inspect_instance.py \
  --config config.toml \
  --instance-id wasm3.ossfuzz-42496369 \
  --offline
```

If you are running from an automation shell where `conda activate` is not available, call the environment Python directly:

```bash
/opt/anaconda3/envs/secb/bin/python read_data/inspect_instance.py \
  --config config.toml \
  --instance-id wasm3.ossfuzz-42496369 \
  --offline
```

## What The Script Prints

- Dataset split and selected row metadata.
- Expected Docker image name.
- Docker image working directory and environment.
- `/usr/local/bin/secb` from the container.
- Repository commit in the container.
- Known execution-path source snippets for currently profiled examples:
  - `wasm3.ossfuzz-42496369`
  - `njs.cve-2022-32414`

## Notes

- PoC tasks use the `:poc` image tag.
- Patch tasks use the `:patch` image tag.
- By default the script uses the local Hugging Face cache under `.cache/huggingface`.
