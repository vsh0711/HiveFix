import subprocess
import tempfile

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from .. import identity
from ..audit import append_audit, audit_event
from ..config import settings
from ..diff_utils import repair_diff
from ..llm_utils import invoke_with_retry, parse_json_response
from ..models.state import RunState

_SYSTEM = """You are a senior engineer fixing a bug. You are given an issue summary,
retrieved code context (file paths + snippets), and — on retry — either the previous
patch's sandbox test failure, or a `git apply` error if the previous patch was
malformed. Produce a minimal fix as a single unified diff (git apply --whitespace=fix
compatible), touching only the files necessary.

Context snippets are exact source lines from the real file — match them character for
character in unchanged (context) lines, and make sure each hunk's `@@ -a,b +c,d @@`
line counts (b and d) equal the actual number of context+changed lines that follow it
in that hunk.

Before finalizing, mentally execute your patched code against the issue's own
reported reproduction (the specific inputs and the expected vs. actual output it
describes) line by line, tracking which branch executes and what each variable holds
— don't just confirm the change "looks like" a fix for the described symptom. If that
trace doesn't actually produce the expected output, the patch is wrong even if the
diff mechanics are perfect: derive a different fix, trace that one too, and only
output a patch whose traced result matches what the issue says is expected.

Respond ONLY with JSON: {"patch_diff": str, "rationale": str}
`patch_diff` must be a valid unified diff starting with `--- a/<path>` / `+++ b/<path>`
headers for each file changed."""

_MAX_LOCAL_VALIDATION_ATTEMPTS = 2


def _git_apply_check(repo_path: str, patch_diff: str) -> str | None:
    """Dry-run validates a diff against the real clone. Returns None if it applies
    cleanly, otherwise the git error — this catches hallucinated context lines and
    wrong hunk-header line counts (both common LLM diff-generation failure modes)
    before wasting a sandbox dispatch round-trip on a patch that can't even apply."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as fh:
        fh.write(patch_diff)
        patch_path = fh.name

    result = subprocess.run(
        ["git", "apply", "--check", "--whitespace=fix", patch_path],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    return None if result.returncode == 0 else result.stderr.strip()


def patch_node(state: RunState) -> RunState:
    node_identity = identity.PATCH
    llm = ChatGroq(
        model=settings.groq_model, api_key=settings.groq_api_key, temperature=0, max_tokens=settings.groq_max_tokens
    )

    context_block = "\n\n".join(
        f"# {h['file_path']} ({h.get('symbol') or 'module'})\n{h['snippet']}" for h in state.get("retrieval_hits", [])
    )

    retry_block = ""
    prior = state.get("sandbox_result")
    if prior and not prior.get("passed"):
        retry_block = (
            f"\n\nThe previous patch failed the sandbox test run "
            f"(conclusion: {prior.get('conclusion')}). Previous patch:\n{state.get('patch_diff', '')}\n"
            "Produce a different, corrected patch."
        )

    attempt = state.get("attempt", 0) + 1
    base_messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(
            content=(
                f"Issue summary:\n{state['triage_summary']}\n\n"
                f"Retrieved context:\n{context_block}"
                f"{retry_block}"
            )
        ),
    ]

    parsed: dict = {}
    validation_errors: list[str] = []
    validated = False
    messages = list(base_messages)

    for local_attempt in range(_MAX_LOCAL_VALIDATION_ATTEMPTS):
        response = invoke_with_retry(
            llm,
            messages,
            config={
                "tags": [node_identity.name],
                "run_name": node_identity.name,
                "metadata": {"run_id": state["run_id"], "node": node_identity.name, "attempt": attempt},
            },
        )
        parsed = parse_json_response(response.content) or {"patch_diff": "", "rationale": response.content}

        diff = parsed.get("patch_diff", "")
        if not diff:
            break

        # Hunk positions, counts, and context are all mechanically determined by the
        # real file — smaller models reliably get the changed code right but are
        # unreliable about this bookkeeping, so repair it before even checking rather
        # than spending a retry asking the model to recompute it by hand.
        diff = repair_diff(diff, state["clone_path"])
        parsed["patch_diff"] = diff

        git_error = _git_apply_check(state["clone_path"], diff)
        if git_error is None:
            validated = True
            break

        validation_errors.append(git_error)
        if local_attempt < _MAX_LOCAL_VALIDATION_ATTEMPTS - 1:
            messages = base_messages + [
                HumanMessage(
                    content=(
                        f"That patch failed `git apply --check` with:\n{git_error}\n\n"
                        "Fix the diff so it applies cleanly — check hunk header line counts "
                        "and that context lines match the source exactly."
                    )
                )
            ]

    if parsed.get("patch_diff"):
        status = "ok" if validated else "unvalidated_patch"
    else:
        status = "empty_patch"

    entry = audit_event(
        node_identity,
        action="draft_patch",
        detail={
            "attempt": attempt,
            "diff_lines": len(parsed.get("patch_diff", "").splitlines()),
            "local_validation_errors": validation_errors,
        },
        status=status,
    )

    return {
        **state,
        "patch_diff": parsed.get("patch_diff", ""),
        "patch_rationale": parsed.get("rationale", ""),
        "attempt": attempt,
        "status": "patched",
        "audit_log": append_audit(state, entry),
    }
