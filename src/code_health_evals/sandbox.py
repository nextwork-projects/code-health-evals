"""E2B templates and the oracle check.

    uv run python -m code_health_evals.sandbox build-swebench swe-7521
    uv run python -m code_health_evals.sandbox oracle swe-7521

The oracle check runs a case's known-good tests (FAIL_TO_PASS) in the sandbox:
they must fail on the buggy state and pass on the fixed state. If they do not,
the case or the sandbox is broken, and the case's label can't be trusted.

SWE-bench cases run in one template per instance image.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import time

from .cases import ROOT, load_cases
from .models import Case

MEMORY_MB = 4096  # the default sandbox has 512 MiB
CPU_COUNT = 2


def template_name(case: Case) -> str:
    return f"swebench-pytest-{case.oracle['version'].replace('.', '-')}-{case.meta['instance_id'].rsplit('-', 1)[1]}"


def build_swebench(case: Case):
    """One template per SWE-bench instance image. /testbed sits at base_commit with conda env `testbed`."""
    from e2b import Template

    template = (
        Template()
        .from_image(case.oracle["image"])
        .set_user("root")
        .set_workdir("/testbed")
        # For a coverage check. The build has internet; sandboxes do not.
        .run_cmd("/opt/miniconda3/envs/testbed/bin/python -m pip install -q coverage")
    )
    t0 = time.perf_counter()
    info = Template.build(
        template,
        template_name(case),
        cpu_count=CPU_COUNT,
        memory_mb=MEMORY_MB,
        on_build_logs=lambda e: print(e),
    )
    print(f"built {template_name(case)} in {time.perf_counter() - t0:.0f}s:", info)
    return info


COV_JSON = "/tmp/cov.json"
COV_RC = "/tmp/covrc"


def pytest_cmd(ids: list[str], cov_source: str | None) -> str:
    """Run only the oracle tests; under coverage when `cov_source` is set."""
    args = "-rA -p no:cacheprovider " + " ".join(shlex.quote(t) for t in ids)
    if not cov_source:
        return f"python -m pytest {args}"
    # pytest's own coverage config sets parallel = 1, which leaves `coverage json` nothing
    # to report; an empty rcfile (written by write_covrc) overrides it.
    rc = f"--rcfile={COV_RC}"
    return (
        f"python -m coverage run {rc} --source={cov_source} -m pytest {args}; "
        f"python -m coverage json {rc} -o {COV_JSON}"
    )


def write_covrc(sbx) -> None:
    sbx.files.write(COV_RC, "[run]\n")


RESULT_RE = re.compile(r"^(PASSED|FAILED|ERROR|XFAIL|XPASS|SKIPPED) (\S+)", re.M)


def parse_results(stdout: str) -> dict[str, str]:
    """`pytest -rA` short summary lines -> {test id: outcome}."""
    return {m[2]: m[1] for m in RESULT_RE.finditer(stdout)}


def outcome(results: dict[str, str], test_id: str) -> str:
    """A test id without parameters stands for all its parametrized runs: one failure fails it."""
    if test_id in results:
        return results[test_id]
    runs = [v for k, v in results.items() if k.startswith(test_id + "[")]
    if not runs:
        return "MISSING"
    return "PASSED" if all(v == "PASSED" for v in runs) else next(v for v in runs if v != "PASSED")


def run_eval(sbx, case: Case, apply_gold: bool, coverage: bool = False) -> dict[str, str]:
    if apply_gold:
        sbx.files.write("/tmp/gold.patch", case.oracle["gold_patch"])
        sbx.commands.run("cd /testbed && git apply /tmp/gold.patch", user="root")
    script = case.oracle["eval_script"]
    if coverage:
        cmd = pytest_cmd(case.oracle["fail_to_pass"], "/testbed/src")
        script = re.sub(r"^pytest -rA .*$", lambda _: cmd, script, count=1, flags=re.M)
    sbx.files.write("/tmp/eval.sh", script)
    r = sbx.commands.run("bash /tmp/eval.sh", user="root", timeout=1800)
    return parse_results(r.stdout)


def oracle_check(case: Case) -> dict:
    """Run a case's tests on both states; `passed` means they fail on buggy and pass on fixed."""
    from e2b import Sandbox

    f2p = case.oracle["fail_to_pass"]
    out: dict = {"case": case.id, "fail_to_pass": f2p}
    for state, gold in (("buggy", False), ("fixed", True)):
        # No internet: the image already holds everything the tests need.
        sbx = Sandbox.create(template_name(case), timeout=1800, allow_internet_access=False)
        try:
            cov = not gold  # the coverage check runs on the buggy state
            if cov:
                write_covrc(sbx)
            res = run_eval(sbx, case, apply_gold=gold, coverage=cov)
            out[state] = {t: outcome(res, t) for t in f2p}
            if cov:
                out["coverage"] = label_coverage(case, json.loads(sbx.files.read(COV_JSON)))
        finally:
            sbx.kill()
    out["passed"] = all(v != "PASSED" for v in out["buggy"].values()) and all(
        v == "PASSED" for v in out["fixed"].values()
    )
    out["covered"] = all(not c["missed"] and c["executable"] for c in out["coverage"])
    return out


def label_coverage(case: Case, cov: dict) -> list[dict]:
    """The failing tests must execute every executable line of each label's primary range.

    Coverage counts a statement on its first line, so blank lines, comments, and the
    inner lines of a multi-line statement are not executable. A range with no executable
    line is judged by the statement it sits in (the nearest executable line above it);
    `statement` records that line. A file the tests never import has no executable line.
    """
    out = []
    for lb in case.labels:
        f = cov["files"].get(lb.file, {})
        missing = set(f.get("missing_lines", []))
        executable = set(f.get("executed_lines", [])) | missing
        start, end = lb.start_line, lb.end_line or lb.start_line
        rng = set(range(start, end + 1))
        row = {"file": lb.file, "range": [start, end], "executable": len(rng & executable)}
        above = [n for n in executable if n < start]
        if not rng & executable and above:
            row["statement"] = max(above)
            rng = {row["statement"]}
            row["executable"] = 1
        row["missed"] = sorted(rng & missing)
        out.append(row)
    return out


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=["build-swebench", "oracle"])
    ap.add_argument("case_id", nargs="?", default="swe-7521")
    args = ap.parse_args()
    case = next((c for c in load_cases(["swebench_reverse"]) if c.id == args.case_id), None)
    if case is None:
        raise SystemExit(f"{args.case_id} is not in data/cases/swebench_reverse.jsonl; run build_dataset first")
    if args.command == "build-swebench":
        build_swebench(case)
    else:
        print(oracle_check(case))


if __name__ == "__main__":
    main()
