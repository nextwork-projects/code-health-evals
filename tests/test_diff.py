from code_health_evals.diff import annotate_diff, changed_old_ranges, invert, new_side_lines, parse

ADD_ONLY = """diff --git a/src/_pytest/capture.py b/src/_pytest/capture.py
--- a/src/_pytest/capture.py
+++ b/src/_pytest/capture.py
@@ -447,6 +447,10 @@ def name(self):
         \"\"\"Ensure that file.name is a string.\"\"\"
         return repr(self.buffer)

+    @property
+    def mode(self):
+        return self.buffer.mode.replace("b", "")
+
     def __getattr__(self, name):
         return getattr(object.__getattribute__(self, "buffer"), name)

"""

TWO_FILES = """diff --git a/src/a.py b/src/a.py
--- a/src/a.py
+++ b/src/a.py
@@ -10,3 +10,3 @@ def f():
     x = 1
-    return x + 1
+    return x - 1
     # end
diff --git a/src/b.py b/src/b.py
new file mode 100644
--- /dev/null
+++ b/src/b.py
@@ -0,0 +1,2 @@
+-- not a header
+y = 2
"""


def test_parse_two_files_and_new_file():
    files = parse(TWO_FILES)
    assert [f.path for f in files] == ["src/a.py", "src/b.py"]
    assert files[1].old_path is None
    assert files[1].hunks[0].lines == ["+-- not a header", "+y = 2"]


def test_removed_line_that_looks_like_a_header():
    diff = """--- a/x.sql
+++ b/x.sql
@@ -1,2 +1,1 @@
--- old comment
 select 1;
"""
    files = parse(diff)
    assert len(files) == 1
    assert files[0].hunks[0].lines == ["--- old comment", " select 1;"]


def test_new_side_lines_include_context_and_additions():
    lines = new_side_lines(TWO_FILES)
    assert lines["src/a.py"] == {10, 11, 12}
    assert lines["src/b.py"] == {1, 2}


def test_changed_old_ranges_for_edit_and_insertion():
    assert changed_old_ranges(TWO_FILES) == [("src/a.py", 11, 11)]
    # pure insertion after old line 449: the bug is the missing code at 449-450
    assert changed_old_ranges(ADD_ONLY) == [("src/_pytest/capture.py", 449, 450)]


def test_invert_swaps_sides():
    inv = invert(TWO_FILES)
    a = parse(inv)[0]
    assert a.hunks[0].lines == ["     x = 1", "-    return x - 1", "+    return x + 1", "     # end"]
    b = parse(inv)[1]
    assert b.old_path == "src/b.py" and b.new_path is None
    assert "deleted file mode 100644" in inv


def test_invert_twice_is_identity_on_hunks():
    twice = parse(invert(invert(ADD_ONLY)))
    once = parse(ADD_ONLY)
    assert [(h.old_start, h.new_start, h.lines) for h in twice[0].hunks] == [
        (h.old_start, h.new_start, h.lines) for h in once[0].hunks
    ]


def test_inverted_insertion_shows_buggy_side_lines():
    # The reviewer sees the inverse of a gold fix; its new side is the buggy file.
    lines = new_side_lines(invert(ADD_ONLY))["src/_pytest/capture.py"]
    assert lines == {447, 448, 449, 450, 451, 452}


def test_annotate_diff_numbers_new_side_lines():
    diff = """diff --git a/src/a.py b/src/a.py
--- a/src/a.py
+++ b/src/a.py
@@ -10,3 +10,3 @@ def f():
     x = 1
-    return x + 1
+    return x - 1
     # end
"""
    lines = annotate_diff(diff).splitlines()
    assert lines[:4] == diff.splitlines()[:4]  # headers unchanged
    assert lines[4] == "   10      x = 1"
    assert lines[5] == "----- -    return x + 1"
    assert lines[6] == "   11 +    return x - 1"
    assert lines[7] == "   12      # end"
