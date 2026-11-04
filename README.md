# Code Health Evals

Starter code for the NextWork Project **Build Code Evals with E2B and Langfuse**.

An AI code reviewer can sound right and still miss the bug. In this Project you build the dataset that measures it: 143 real pull request cases with labels that say where each bug is. You prove a case by running its tests in an E2B sandbox, write labels of your own, have a second model cross-check labels, and sync the dataset to Langfuse.

The `solution` branch has the finished Project, and the `secret-mission` branch adds the Secret Mission.

## What's in the repo

| Path | What it is |
|---|---|
| `src/code_health_evals/build_dataset.py` | Builds the `swebench_reverse` and `qodo` slices. You finish `build_swebench` and `assign_splits` here |
| `src/code_health_evals/sandbox.py` | E2B template builds and test helpers. You write `oracle_check` here |
| `src/code_health_evals/label_qa.py` | The second-model label cross-check |
| `src/code_health_evals/cases.py` | Loads cases, and turns a case into a Langfuse dataset item with `to_item` |
| `src/code_health_evals/diff.py` | Diff tools, including `invert`, which reverses a patch |
| `src/code_health_evals/models.py` | The `Case` and `Label` shapes |
| `scripts/check_keys.py` | Checks your OpenRouter, Langfuse and E2B keys |
| `data/raw/` | SWE-bench Verified pytest rows and Qodo PR-Review-Bench PRs |
| `data/cases/` | The ready-made `fresh`, `clean` and `swebench_origin` slices. The slices you build land here too |
| `data/candidates/learner.jsonl` | Two real pydantic PRs for you to label |
| `data/labels/my_labels.json` | Where your labels go |
| `data/label_qa/` | Cross-check votes on the Qodo, `fresh` and `swebench_origin` labels |
| `tests/` | Offline tests for the provided helpers |

You write `src/code_health_evals/sync_langfuse.py` during the Project.

## Set up

You need OpenRouter, Langfuse and E2B accounts, and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
uv sync
cp .env.example .env   # then fill it in
uv run scripts/check_keys.py .env
```

## Tests

```bash
uv run pytest
```

## Data sources

- [SWE-bench Verified](https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified): the `pytest-dev/pytest` rows.
- [Qodo PR-Review-Bench](https://huggingface.co/datasets/Qodo/PR-Review-Bench): 100 PRs with their labeled issues.
