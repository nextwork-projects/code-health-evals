"""Cross-check every label with a model from a family the series never uses.

    uv run python -m code_health_evals.label_qa --slices swebench_reverse

The checker (LABEL_QA_MODEL) comes from a model family the series never reviews
or judges with. It sees what the reviewer never sees (the issue text and gold
fix, or Qodo's issue record) and votes on each label. Votes never change a label:
disagreements go to data/label_qa/disagreements.md for a human to settle.

Responses are cached in results/cache/label_qa/, so a re-run costs nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .build_dataset import RAW, read_jsonl
from .cases import ROOT, load_cases
from .diff import annotate_diff, parse
from .models import Case

OUT = ROOT / "data" / "label_qa"
CACHE = ROOT / "results" / "cache" / "label_qa"
DEFAULT_MODEL = "openai/gpt-6.1-terra"
OPENROUTER_URL = "https://openrouter.ai/api/v1"
LINE_TOLERANCE = 3

PROMPT = """You are auditing the ground-truth labels of a code-review benchmark. A reviewer model will see only the diff below. Each label says where in the diff a correct reviewer should flag a bug.

Line numbers are new-side line numbers (the PR's head), printed at the start of each diff line. Removed lines show `-----`; a bug caused by removed code is labeled at the nearest new-side line.

For each label, decide:
- `agree`: the file and line range cover the code that causes the described problem, or the spot a reviewer should comment on.
- `disagree`: the location is wrong. Give the file and line range you would use.
- `unsure`: the evidence is not enough to tell.
For a label with no location, propose one, and use `disagree` with your location (or `unsure` if you cannot find it).
Judge the location and whether the label describes a real problem in this diff. For a repo-rule label, the quoted rule decides what counts: a violation of that rule is a real problem even when it looks like style. A label may list `also` ranges: other places a reviewer may fairly cite for the same bug. Judge the primary range as the cause.

## Evidence about the bugs (the reviewer never sees this)

{evidence}

## Labels

{labels}

## Diff

```diff
{diff}
```
"""


class LabelVerdict(BaseModel):
    index: int = Field(description="The label's index from the list")
    verdict: Literal["agree", "disagree", "unsure"]
    file: str | None = Field(None, description="Your file, when you disagree")
    start_line: int | None = None
    end_line: int | None = None
    reason: str = Field(description="One sentence")


class LabelQA(BaseModel):
    verdicts: list[LabelVerdict]


def _raw_index() -> dict[str, dict]:
    idx: dict[str, dict] = {}
    for r in read_jsonl(RAW / "swebench_verified_pytest.jsonl"):
        idx[r["instance_id"]] = r
    for r in read_jsonl(RAW / "qodo_pr_review_bench.jsonl"):
        n = r["pr_url_to_review"].rstrip("/").rsplit("/", 1)[1]
        idx[f"qodo-{r['repo']}-{n}"] = r
    return idx


def _rules() -> dict[str, dict[str, str]]:
    """Qodo repo -> rule title -> the rule's full text."""
    out: dict[str, dict[str, str]] = {}
    for r in read_jsonl(RAW / "qodo_rules_for_repo.jsonl"):
        repo = json.loads(r["repo"]) if r["repo"].startswith('"') else r["repo"]
        rules = json.loads(r["extracted_rules"]) if isinstance(r["extracted_rules"], str) else r["extracted_rules"]
        out[repo] = {
            x["title"]: f"{x['objective']} Passes when: {x['success_criteria']} Fails when: {x['failure_criteria']}"
            for x in rules
        }
    return out


def evidence(case: Case, raw: dict) -> str:
    if case.slice == "swebench_reverse":
        return (
            f"Issue report:\n{raw['problem_statement'][:4000]}\n\n"
            "The gold fix (the reviewer sees this change reversed, so the diff below introduces the bug):\n"
            f"```diff\n{raw['patch']}\n```"
        )
    rules = _rules().get(raw["repo"], {})
    lines = []
    for i, iss in enumerate(raw["issues"]):
        rule = ""
        if iss.get("rule_name"):
            text = rules.get(iss["rule_name"]) or "Rule text not found. This repo's rules: " + "; ".join(rules)
            rule = f"\nViolates repo rule \"{iss['rule_name']}\": {text}"
        lines.append(
            f"[{i}] {iss['title']}\n{iss.get('description', '')}{rule}\n"
            f"Problematic code: {iss.get('problematic_code_snippet') or '(none given)'}"
        )
    return "\n\n".join(lines)


def scoped_diff(case: Case) -> str:
    """Only the files that carry labels, unless a label has no file."""
    if any(lb.file is None for lb in case.labels):
        return annotate_diff(case.diff)
    files = {lb.file for lb in case.labels} | {a.file for lb in case.labels for a in lb.also}
    keep = []
    for fp in parse(case.diff):
        if fp.path in files:
            keep.append(f"--- a/{fp.old_path}" if fp.old_path else "--- /dev/null")
            keep.append(f"+++ b/{fp.new_path}" if fp.new_path else "+++ /dev/null")
            for h in fp.hunks:
                keep.append(f"@@ -{h.old_start},{h.old_len} +{h.new_start},{h.new_len} @@{h.header}")
                keep.extend(h.lines)
    return annotate_diff("\n".join(keep))


def render(case: Case, raw: dict) -> str:
    def loc(lb) -> str:
        also = "".join(f"; also {a.file}:{a.start_line}-{a.end_line}" for a in lb.also)
        return f"{lb.file or '(no file)'}:{lb.start_line or '?'}-{lb.end_line or lb.start_line or '?'}{also}"

    labels = "\n".join(f"[{i}] ({lb.kind}) {loc(lb)}  {lb.description}" for i, lb in enumerate(case.labels))
    return PROMPT.format(evidence=evidence(case, raw), labels=labels, diff=scoped_diff(case))


def make_llm(model: str):
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=model,
        base_url=OPENROUTER_URL,
        api_key=os.environ["OPENROUTER_API_KEY"],
        max_retries=3,
        timeout=300,
        extra_body={
            "provider": {"require_parameters": True},
            "reasoning": {"effort": "medium"},
            "usage": {"include": True},
        },
    )
    return llm.with_structured_output(LabelQA, method="json_schema", include_raw=True)


def check_case(case: Case, raw: dict, llm, model: str) -> dict:
    prompt = render(case, raw)
    key = hashlib.sha256(f"{model}\n{prompt}".encode()).hexdigest()[:24]
    cached = CACHE / f"{key}.json"
    if cached.exists():
        return json.loads(cached.read_text()) | {"cached": True}
    res = llm.invoke(prompt)
    raw_msg = res["raw"]
    usage = dict(getattr(raw_msg, "usage_metadata", None) or {})
    cost = (getattr(raw_msg, "response_metadata", None) or {}).get("token_usage", {}).get("cost")
    parsed: LabelQA | None = res["parsed"]
    out = {
        "case_id": case.id,
        "verdicts": [v.model_dump() for v in parsed.verdicts] if parsed else [],
        "error": None if parsed else str(res.get("parsing_error")),
        "usage": usage,
        "cost": cost,
    }
    if parsed:
        CACHE.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(out))
    return out


def within_tolerance(lb, v: dict) -> bool:
    """A moved range that still overlaps the label's ±tolerance window changes no score."""
    if not (lb.file and lb.start_line and v.get("file") == lb.file and v.get("start_line")):
        return False
    end = lb.end_line or lb.start_line
    v_end = v.get("end_line") or v["start_line"]
    return v["start_line"] <= end + LINE_TOLERANCE and v_end >= lb.start_line - LINE_TOLERANCE


def rows_for(case: Case, result: dict) -> list[dict]:
    by_index = {v["index"]: v for v in result["verdicts"]}
    rows = []
    for i, lb in enumerate(case.labels):
        v = dict(by_index.get(i, {"verdict": "missing", "reason": "the checker returned no verdict"}))
        if v["verdict"] == "disagree" and within_tolerance(lb, v):
            v["verdict"], v["reason"] = "agree", f"within the ±{LINE_TOLERANCE}-line match tolerance. " + v["reason"]
        rows.append({"case_id": case.id, "slice": case.slice, "index": i, "label": lb.model_dump(), **v})
    return rows


def write_report(all_rows: list[dict], model: str) -> Path:
    bad = [r for r in all_rows if r["verdict"] != "agree"]
    lines = [
        "# Label cross-check: disagreements",
        "",
        f"Checker: `{model}`. {len(all_rows)} labels checked, {len(bad)} not agreed. "
        "Labels are unchanged; settle each row by hand.",
        "",
        "| Case | # | Label | Verdict | Checker's location | Reason |",
        "|---|---|---|---|---|---|",
    ]
    for r in bad:
        lb = r["label"]
        loc = f"`{lb['file']}:{lb['start_line']}-{lb['end_line']}`" if lb["file"] else "(none)"
        mine = f"`{r.get('file')}:{r.get('start_line')}-{r.get('end_line')}`" if r.get("file") else ""
        desc = lb["description"].replace("|", "\\|")[:80]
        reason = (r.get("reason") or "").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {r['case_id']} | {r['index']} | {loc} {desc} | {r['verdict']} | {mine} | {reason} |")
    path = OUT / "disagreements.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--slices", nargs="*", default=["swebench_reverse"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--model", default=os.environ.get("LABEL_QA_MODEL", DEFAULT_MODEL))
    ap.add_argument("--concurrency", type=int, default=6)
    args = ap.parse_args()

    raw = _raw_index()
    llm = make_llm(args.model)
    OUT.mkdir(parents=True, exist_ok=True)
    cost = 0.0
    for name in args.slices:
        cases = [c for c in load_cases([name], limit=args.limit) if c.labels]

        def run(c: Case) -> dict:
            key = c.meta.get("instance_id") or c.id
            return check_case(c, raw.get(key, {}), llm, args.model)

        with ThreadPoolExecutor(args.concurrency) as pool:
            results = list(pool.map(run, cases))
        rows = [row for c, r in zip(cases, results) for row in rows_for(c, r)]
        with open(OUT / f"{name}.jsonl", "w") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")
        spent = sum(r["cost"] or 0 for r in results if not r.get("cached"))
        cost += spent
        counts = {k: sum(1 for r in rows if r["verdict"] == k) for k in ("agree", "disagree", "unsure", "missing")}
        print(f"{name}: {len(rows)} labels {counts}, errors {sum(1 for r in results if r['error'])}, ${spent:.4f}")

    all_rows = [json.loads(line) for p in sorted(OUT.glob("*.jsonl")) for line in p.read_text().splitlines()]
    print("report:", write_report(all_rows, args.model).relative_to(ROOT), f"| spent this run ${cost:.4f}")


if __name__ == "__main__":
    main()
