"""Push data/cases/ to Langfuse datasets, one per split: code-review-dev, code-review-heldout.

    uv run python -m code_health_evals.sync_langfuse

Item ids are the case ids, so re-running updates items instead of duplicating them.
The JSONL in the repo stays the source of truth.
"""

from __future__ import annotations

from .cases import ROOT, load_cases, to_item


def main() -> None:
    from dotenv import load_dotenv
    from langfuse import get_client

    load_dotenv(ROOT / ".env")
    lf = get_client()
    for split in ("dev", "heldout"):
        name = f"code-review-{split}"
        cases = load_cases(split=split)
        lf.create_dataset(name=name, description=f"PR review cases, {split} split", metadata={"source": "data/cases"})
        for c in cases:
            item = to_item(c)
            lf.create_dataset_item(
                dataset_name=name,
                id=c.id,
                input=item["input"],
                expected_output=item["expected_output"],
                metadata=item["metadata"],
            )
        print(f"{name}: {len(cases)} items")
    lf.flush()


if __name__ == "__main__":
    main()
