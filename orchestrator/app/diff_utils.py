"""Repairs LLM-generated unified diffs before they ever reach `git apply`. Smaller
models reliably get the changed code right but are unreliable about the mechanical
parts of a diff: hunk header line counts, the claimed starting line number, and —
less obviously — supplying enough context for `git apply` to disambiguate the hunk's
location. All three are fully determined by the hunk's own content plus the real
target file, so none of them are worth spending another model call on.

On the context point specifically: `git apply` can refuse a hunk with zero trailing
context even when its content and claimed position are exactly correct, if a
similarly-shaped block appears later in the file (e.g. sibling functions with a
similar def/docstring/return shape) — empirically confirmed against git 2.54. Padding
every hunk with a couple of real lines of context on each side fixes this.
"""

import os
import re

_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")
_FILE_HEADER_RE = re.compile(r"^--- a/(.+)$")

_CONTEXT_PAD = 2


def _find_subsequence(haystack: list[str], needle: list[str], search_from: int) -> int:
    """0-based index in `haystack` where `needle` occurs as a contiguous
    subsequence, searching from `search_from` onward, or -1 if not found."""
    if not needle:
        return search_from
    limit = len(haystack) - len(needle)
    for start in range(search_from, limit + 1):
        if haystack[start : start + len(needle)] == needle:
            return start
    return -1


def repair_diff(diff_text: str, repo_path: str) -> str:
    """Rewrites each hunk to: (1) anchor its starting line to where its old-file
    content actually occurs in the real file, trusting the file over the model's
    self-reported numbers, (2) pad it with a couple of lines of real context on each
    side so `git apply` isn't left to disambiguate a zero-context hunk, and
    (3) recompute the header's line counts to match. A hunk whose content can't be
    found verbatim in the file is left untouched — that's a genuine content
    hallucination no mechanical fix can repair, and `git apply` will report a clear
    error for it.
    """
    lines = diff_text.splitlines()
    out: list[str] = []
    i = 0
    current_file: list[str] | None = None
    search_cursor = 0
    net_offset = 0  # cumulative (added - removed) from earlier hunks in this file

    while i < len(lines):
        line = lines[i]

        file_match = _FILE_HEADER_RE.match(line)
        if file_match:
            rel_path = file_match.group(1)
            try:
                with open(os.path.join(repo_path, rel_path), "r", encoding="utf-8", errors="ignore") as fh:
                    current_file = fh.read().splitlines()
            except OSError:
                current_file = None
            search_cursor = 0
            net_offset = 0
            out.append(line)
            i += 1
            continue

        match = _HUNK_HEADER_RE.match(line)
        if not match:
            out.append(line)
            i += 1
            continue

        old_start, _old_count, _new_start, _new_count, trailer = match.groups()
        body_start = i + 1
        j = body_start
        body: list[tuple[str, str]] = []  # (tag, content) for each original hunk line
        old_body_lines: list[str] = []
        while j < len(lines) and lines[j] and lines[j][0] in " +-\\":
            tag, content = lines[j][0], lines[j][1:]
            body.append((tag, content))
            if tag in (" ", "-"):
                old_body_lines.append(content)
            j += 1

        resolved_old_start = int(old_start)
        pad_before = pad_after = 0
        if current_file is not None and old_body_lines:
            match_idx = _find_subsequence(current_file, old_body_lines, search_cursor)
            if match_idx != -1:
                resolved_old_start = match_idx + 1
                pad_before = min(_CONTEXT_PAD, match_idx)
                pad_after = min(_CONTEXT_PAD, len(current_file) - (match_idx + len(old_body_lines)))
                search_cursor = match_idx + len(old_body_lines) + pad_after

        if pad_before:
            lead = [(" ", l) for l in current_file[resolved_old_start - 1 - pad_before : resolved_old_start - 1]]
            body = lead + body
            resolved_old_start -= pad_before
        if pad_after:
            end_of_old_content = (resolved_old_start - 1) + sum(1 for t, _ in body if t in (" ", "-"))
            trail = [(" ", l) for l in current_file[end_of_old_content : end_of_old_content + pad_after]]
            body = body + trail

        old_count = sum(1 for t, _ in body if t in (" ", "-"))
        new_count = sum(1 for t, _ in body if t in (" ", "+"))
        resolved_new_start = resolved_old_start + net_offset
        net_offset += new_count - old_count

        out.append(f"@@ -{resolved_old_start},{old_count} +{resolved_new_start},{new_count} @@{trailer}")
        out.extend(f"{tag}{content}" for tag, content in body)
        i = j

    fixed = "\n".join(out)
    if diff_text.endswith("\n") and not fixed.endswith("\n"):
        fixed += "\n"
    return fixed


# Kept as a standalone, repo-independent utility: a pure header-count fix with no
# file access, for callers that just want the mechanical count fixed.
def fix_hunk_header_counts(diff_text: str) -> str:
    lines = diff_text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        match = _HUNK_HEADER_RE.match(line)
        if not match:
            out.append(line)
            i += 1
            continue

        old_start, _old_count, new_start, _new_count, trailer = match.groups()
        body_start = i + 1
        j = body_start
        old_count = new_count = 0
        while j < len(lines) and lines[j] and lines[j][0] in " +-\\":
            tag = lines[j][0]
            if tag in (" ", "-"):
                old_count += 1
            if tag in (" ", "+"):
                new_count += 1
            j += 1

        out.append(f"@@ -{old_start},{old_count} +{new_start},{new_count} @@{trailer}")
        out.extend(lines[body_start:j])
        i = j

    fixed = "\n".join(out)
    if diff_text.endswith("\n") and not fixed.endswith("\n"):
        fixed += "\n"
    return fixed
