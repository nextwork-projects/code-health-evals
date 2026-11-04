"""Build data/cases/*.jsonl from the raw sources in data/raw/.

    uv run python -m code_health_evals.build_dataset

Slices built here:
- swebench_reverse: all 19 SWE-bench Verified pytest instances. The PR is the gold
  fix reversed, applied on the fixed state; its new side is the buggy `base_commit`.
- qodo: all 100 Qodo PR-Review-Bench PRs, with diffs from data/raw/qodo_diffs/.

The fresh, clean, and swebench_origin slices ship ready-made in data/cases/.

label_qa.py cross-checks the labels; a human settles the disagreements.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .cases import CASES, ROOT
from .diff import changed_old_ranges, invert
from .models import Case, Label, Location

RAW = ROOT / "data" / "raw"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_cases(name: str, cases: list[Case]) -> None:
    CASES.mkdir(parents=True, exist_ok=True)
    with open(CASES / f"{name}.jsonl", "w") as fh:
        for c in cases:
            fh.write(c.model_dump_json() + "\n")


def first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:200]
    return ""


def assign_splits(cases: list[Case]) -> None:
    """50/50 dev and held-out within a slice, stable across rebuilds (hash order, then alternate)."""
    # TODO: sort the cases by the SHA-256 of their id, then alternate "dev" and "heldout".


PRIMARY = ROOT / "data" / "labels" / "swebench_primary.json"


def one_bug_label(case_id: str, r: dict) -> Label:
    """One label per bug: the cause range, with the fix's other hunks as `also` ranges.

    The cause comes from data/labels/swebench_primary.json (drafted by the label
    cross-check, settled by a human); without an entry it is the first hunk.
    """
    ranges = changed_old_ranges(r["patch"])
    chosen = json.loads(PRIMARY.read_text()).get(case_id) if PRIMARY.exists() else None
    if chosen:
        f, a, b = chosen["file"], chosen["start_line"], chosen["end_line"]
    else:
        f, a, b = ranges[0]
    also = [Location(file=rf, start_line=ra, end_line=rb) for rf, ra, rb in ranges if (rf, ra, rb) != (f, a, b)]
    return Label(file=f, start_line=a, end_line=b, description=first_line(r["problem_statement"]), also=also)


def build_swebench() -> list[Case]:
    rows = read_jsonl(RAW / "swebench_verified_pytest.jsonl")
    reverse = []
    for r in rows:
        iid = r["instance_id"]
        case_id = f"swe-{iid.rsplit('-', 1)[1]}"
        labels = [one_bug_label(case_id, r)]
        oracle = {
            "fail_to_pass": json.loads(r["FAIL_TO_PASS"]) if isinstance(r["FAIL_TO_PASS"], str) else r["FAIL_TO_PASS"],
            "test_patch": r["test_patch"],
            "image": r["image"],
            "version": r["version"],
            "eval_script": r["eval_script"],
            "gold_patch": r["patch"],
        }
        meta = {"instance_id": iid, "difficulty": r["difficulty"], "created_at": r["created_at"]}
        files = sorted({f for f, _, _ in changed_old_ranges(r["patch"])})
        # TODO: reverse the gold fix with invert(), then add the reverse-fix Case to `reverse`.
    return reverse


def label_qa_votes(slice_name: str) -> dict[tuple[str, int], str]:
    """(case id, label index) -> agreed | disputed, from the last label_qa.py run."""
    path = ROOT / "data" / "label_qa" / f"{slice_name}.jsonl"
    if not path.exists():
        return {}
    return {
        (r["case_id"], r["index"]): "agreed" if r["verdict"] == "agree" else "disputed"
        for r in read_jsonl(path)
    }


def format_rules(raw: str | list | None) -> str | None:
    if not raw:
        return None
    rules = json.loads(raw) if isinstance(raw, str) else raw
    return "\n".join(f"- {x['title']}: {x['objective']} Fails when: {x['failure_criteria']}" for x in rules)


def build_qodo() -> list[Case]:
    rows = read_jsonl(RAW / "qodo_pr_review_bench.jsonl")
    rules = {json.loads(r["repo"]) if r["repo"].startswith('"') else r["repo"]: r["extracted_rules"]
             for r in read_jsonl(RAW / "qodo_rules_for_repo.jsonl")}
    qa = label_qa_votes("qodo")
    cases = []
    for r in rows:
        url = r["pr_url_to_review"]
        n = url.rstrip("/").rsplit("/", 1)[1]
        diff = (RAW / "qodo_diffs" / f"{r['repo']}-{n}.diff").read_text()
        labels = [
            Label(
                file=i.get("file_path"),
                start_line=i.get("start_line"),
                end_line=i.get("end_line"),
                description=i["title"],
                kind="rule" if i.get("rule_name") else "bug",
                qa=qa.get((f"qodo-{r['repo']}-{n}", k)),
            )
            for k, i in enumerate(r["issues"])
        ]
        cases.append(
            Case(
                id=f"qodo-{r['repo']}-{n}",
                slice="qodo",
                repo=url.split("github.com/", 1)[1].rsplit("/pull/", 1)[0],
                pr_url=url,
                title=f"{r['repo']} PR {n}",
                diff=diff,
                labels=labels,
                label_source="dataset",
                meta={"rules": format_rules(rules.get(r["repo"])), "num_of_issues": r["num_of_issues"]},
            )
        )
    return cases


def main() -> None:
    for name, cases in (("swebench_reverse", build_swebench()), ("qodo", build_qodo())):
        assign_splits(cases)
        write_cases(name, cases)
        dev = sum(1 for c in cases if c.split == "dev")
        print(f"{name}: {len(cases)} cases, {dev} dev, {sum(1 for c in cases if c.split == 'heldout')} held-out")


if __name__ == "__main__":
    main()
