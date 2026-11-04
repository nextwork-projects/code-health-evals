"""Load cases from data/cases/ with slice, split, and per-slice limit filters."""

from __future__ import annotations

from pathlib import Path

from .models import Case

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "data" / "cases"


def load_cases(slices: list[str] | None = None, split: str | None = None, limit: int | None = None) -> list[Case]:
    """`limit` caps each slice, so a smoke run still covers every slice."""
    out: list[Case] = []
    for path in sorted(CASES.glob("*.jsonl")):
        if slices and path.stem not in slices:
            continue
        kept = 0
        for line in path.read_text().splitlines():
            if limit and kept >= limit:
                break
            c = Case.model_validate_json(line)
            if c.meta.get("excluded"):
                continue
            if split and c.split != split:
                continue
            out.append(c)
            kept += 1
    return out


def to_item(c: Case) -> dict:
    """A case as a Langfuse dataset item: what the reviewer sees, and what it's scored against."""
    return {
        "input": {"id": c.id, "title": c.title, "diff": c.diff, "rules": c.meta.get("rules")},
        "expected_output": {"labels": [lb.model_dump() for lb in c.labels]},
        "metadata": {"id": c.id, "slice": c.slice, "split": c.split},
    }
