import os
import subprocess
import tempfile

from app.diff_utils import fix_hunk_header_counts, repair_diff


def _init_repo(files: dict[str, str]) -> str:
    tmp = tempfile.mkdtemp()
    for name, content in files.items():
        with open(os.path.join(tmp, name), "w") as fh:
            fh.write(content)
    subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp, check=True)
    return tmp


def _git_apply_check(repo_path: str, diff_text: str) -> bool:
    result = subprocess.run(
        ["git", "apply", "--check", "--whitespace=fix", "-"],
        cwd=repo_path,
        input=diff_text,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def test_fixes_wrong_hunk_counts():
    broken = (
        "--- a/calc.py\n"
        "+++ b/calc.py\n"
        "@@ -6,7 +6,7 @@\n"
        " def subtract(a, b):\n"
        '     """Return the difference of a and b."""\n'
        "-    return a + b\n"
        "+    return a - b\n"
    )
    fixed = fix_hunk_header_counts(broken)
    assert "@@ -6,3 +6,3 @@" in fixed
    assert "    return a + b" in fixed
    assert "    return a - b" in fixed


def test_leaves_correct_header_unchanged():
    correct = "--- a/f.py\n+++ b/f.py\n@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 2\n"
    assert fix_hunk_header_counts(correct) == correct


def test_repair_diff_fixes_wrong_start_line_and_zero_context():
    """Reproduces a real observed failure: the model claims the hunk starts at line 1
    with zero trailing context, but the function is actually at line 6 and a similarly
    shaped sibling function later in the file makes git apply refuse a zero-context
    hunk even when the content and claimed position would otherwise be fine."""
    repo_content = (
        "def add(a, b):\n"
        '    """Return the sum of a and b."""\n'
        "    return a + b\n"
        "\n"
        "\n"
        "def subtract(a, b):\n"
        '    """Return the difference a - b."""\n'
        "    return a + b\n"
        "\n"
        "\n"
        "def multiply(a, b):\n"
        '    """Return the product of a and b."""\n'
        "    return a * b\n"
    )
    repo = _init_repo({"calc.py": repo_content})

    broken = (
        "--- a/calc.py\n"
        "+++ b/calc.py\n"
        "@@ -1,3 +1,3 @@\n"
        " def subtract(a, b):\n"
        '     """Return the difference a - b."""\n'
        "-    return a + b\n"
        "+    return a - b\n"
    )

    assert not _git_apply_check(repo, broken), "fixture should reproduce the real failure before repair"

    fixed = repair_diff(broken, repo)
    assert _git_apply_check(repo, fixed), f"repaired diff should apply cleanly:\n{fixed}"


def test_repair_diff_leaves_unmatchable_hunk_alone():
    repo = _init_repo({"f.py": "def f():\n    return 1\n"})
    hallucinated = "--- a/f.py\n+++ b/f.py\n@@ -1,2 +1,2 @@\n def g():\n-    return 2\n+    return 3\n"
    # Content doesn't exist in the real file at all — repair can't invent a fix,
    # should pass it through unchanged rather than silently producing garbage.
    assert repair_diff(hallucinated, repo) == hallucinated
