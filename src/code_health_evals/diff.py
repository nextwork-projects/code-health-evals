"""Unified-diff helpers: index the lines a diff shows, and invert a patch."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


@dataclass
class Hunk:
    old_start: int
    old_len: int
    new_start: int
    new_len: int
    header: str
    lines: list[str] = field(default_factory=list)  # each keeps its ' ', '+', '-' or '\\' prefix


@dataclass
class FilePatch:
    old_path: str | None  # None for a new file
    new_path: str | None  # None for a deleted file
    preamble: list[str] = field(default_factory=list)  # 'diff --git', 'index', mode lines
    hunks: list[Hunk] = field(default_factory=list)

    @property
    def path(self) -> str:
        return self.new_path or self.old_path or ""


def _strip_prefix(p: str) -> str | None:
    p = p.split("\t", 1)[0].strip()
    if p == "/dev/null":
        return None
    if p.startswith(("a/", "b/")):
        return p[2:]
    return p


def parse(diff: str) -> list[FilePatch]:
    files: list[FilePatch] = []
    cur: FilePatch | None = None
    hunk: Hunk | None = None
    pending_preamble: list[str] = []
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            cur, hunk = None, None
            pending_preamble = [line]
            continue
        # Inside an unfinished hunk, '--- x' is a removed line, not a file header.
        if line.startswith("--- ") and (hunk is None or _hunk_full(hunk)):
            cur = FilePatch(old_path=_strip_prefix(line[4:]), new_path=None, preamble=pending_preamble)
            pending_preamble = []
            files.append(cur)
            hunk = None
            continue
        if line.startswith("+++ ") and cur is not None and hunk is None:
            cur.new_path = _strip_prefix(line[4:])
            continue
        m = HUNK_RE.match(line)
        if m and cur is not None:
            hunk = Hunk(
                old_start=int(m[1]),
                old_len=int(m[2]) if m[2] is not None else 1,
                new_start=int(m[3]),
                new_len=int(m[4]) if m[4] is not None else 1,
                header=m[5],
            )
            cur.hunks.append(hunk)
            continue
        if hunk is not None and line[:1] in (" ", "+", "-", "\\"):
            hunk.lines.append(line)
        elif hunk is not None and line == "":
            hunk.lines.append(" ")  # some tools strip the space on blank context lines
        elif cur is None or hunk is None:
            pending_preamble.append(line)
    return files


def _hunk_full(h: Hunk) -> bool:
    old = sum(1 for ln in h.lines if ln[:1] in (" ", "-"))
    new = sum(1 for ln in h.lines if ln[:1] in (" ", "+"))
    return old >= h.old_len and new >= h.new_len


def new_side_lines(diff: str) -> dict[str, set[int]]:
    """Map each file the diff touches to the new-side line numbers its hunks show.

    A reviewer reading the diff can cite any of these lines, context included.
    """
    out: dict[str, set[int]] = {}
    for fp in parse(diff):
        if fp.new_path is None:
            continue
        seen = out.setdefault(fp.new_path, set())
        for h in fp.hunks:
            n = h.new_start
            for ln in h.lines:
                tag = ln[:1]
                if tag in (" ", "+"):
                    seen.add(n)
                    n += 1
    return out


def annotate_diff(diff: str) -> str:
    """Prefix each hunk line with its new-side line number, so a model can cite lines."""
    out: list[str] = []
    n: int | None = None
    for line in diff.splitlines():
        m = HUNK_RE.match(line)
        if m:
            n = int(m[3])
            out.append(line)
            continue
        if n is None or line.startswith(("diff --git", "--- ", "+++ ", "index ")):
            n = None if line.startswith("diff --git") else n
            out.append(line)
            continue
        tag = line[:1]
        if tag in (" ", "+", ""):
            out.append(f"{n:>5} {line}")
            n += 1
        elif tag == "-":
            out.append(f"----- {line}")
        else:
            out.append(f"      {line}")
    return "\n".join(out)


def changed_old_ranges(patch: str) -> list[tuple[str, int, int]]:
    """For each hunk, the old-side line range the patch changes.

    Used to label the bug in a gold fix: the old side is the buggy state. A hunk
    that only adds lines changed no old line, so its range is the old line the
    insertion sits after.
    """
    out: list[tuple[str, int, int]] = []
    for fp in parse(patch):
        if fp.old_path is None:
            continue
        for h in fp.hunks:
            o = h.old_start
            removed: list[int] = []
            insert_after: int | None = None
            for ln in h.lines:
                tag = ln[:1]
                if tag == " ":
                    o += 1
                elif tag == "-":
                    removed.append(o)
                    o += 1
                elif tag == "+" and insert_after is None:
                    insert_after = max(o - 1, 1)
            if removed:
                out.append((fp.old_path, min(removed), max(removed)))
            elif insert_after is not None:
                out.append((fp.old_path, insert_after, insert_after + 1))
    return out


def invert(patch: str) -> str:
    """Return the patch that undoes `patch` (what `git apply -R` would apply)."""
    out: list[str] = []
    for fp in parse(patch):
        old, new = fp.new_path, fp.old_path
        for p in fp.preamble:
            if p.startswith("diff --git "):
                out.append(f"diff --git a/{old or new} b/{new or old}")
            elif p.startswith("new file mode"):
                out.append(p.replace("new file mode", "deleted file mode"))
            elif p.startswith("deleted file mode"):
                out.append(p.replace("deleted file mode", "new file mode"))
            elif p.startswith("index "):
                m = re.match(r"index (\w+)\.\.(\w+)(.*)", p)
                out.append(f"index {m[2]}..{m[1]}{m[3]}" if m else p)
            else:
                out.append(p)
        out.append(f"--- {'a/' + old if old else '/dev/null'}")
        out.append(f"+++ {'b/' + new if new else '/dev/null'}")
        for h in fp.hunks:
            out.append(f"@@ -{h.new_start},{h.new_len} +{h.old_start},{h.old_len} @@{h.header}")
            # Swap signs, keeping removals before additions in each changed block.
            minus: list[str] = []
            plus: list[str] = []
            for ln in h.lines + [" "]:
                tag = ln[:1]
                if tag == "+":
                    minus.append("-" + ln[1:])
                elif tag == "-":
                    plus.append("+" + ln[1:])
                else:
                    out.extend(minus + plus)
                    minus, plus = [], []
                    out.append(ln)
            out.pop()  # the sentinel
    return "\n".join(out) + "\n"
