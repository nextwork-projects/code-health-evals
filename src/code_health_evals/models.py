"""Data shapes for the dataset and its checks."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Slice = Literal["swebench_reverse", "swebench_origin", "fresh", "clean", "qodo"]
Split = Literal["dev", "heldout"]


class Location(BaseModel):
    file: str
    start_line: int
    end_line: int


class Label(BaseModel):
    """A ground-truth bug: where it is in the PR's head, and what it is.

    The primary range is the code that causes the bug. `also` holds other ranges
    a reviewer may fairly cite for the same bug (supporting hunks of the fix):
    a finding there is a true positive, but the bug still counts once for recall.
    """

    file: str | None
    start_line: int | None
    end_line: int | None
    description: str
    kind: Literal["bug", "rule"] = "bug"  # Qodo also seeds repo-rule violations
    also: list[Location] = Field(default_factory=list)
    qa: Literal["agreed", "disputed"] | None = None  # the second-model cross-check (label_qa.py)


class Case(BaseModel):
    id: str
    slice: Slice
    split: Split | None = None
    repo: str
    pr_url: str | None = None  # the real PR, when there is one
    title: str
    diff: str  # what the reviewer sees
    labels: list[Label] = Field(default_factory=list)  # empty for clean PRs
    buggy_sha: str | None = None  # execution slices only
    fixed_sha: str | None = None
    oracle: dict | None = None  # execution slices: how to prove the bug (FAIL_TO_PASS, test_patch, image)
    label_source: Literal["auto", "reviewed", "dataset"] = "auto"
    meta: dict = Field(default_factory=dict)
