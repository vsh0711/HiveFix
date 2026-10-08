from typing import List, Optional, TypedDict

from pydantic import BaseModel


class RetrievalHit(BaseModel):
    file_path: str
    symbol: Optional[str] = None
    score: float
    snippet: str
    source: str  # "bm25" | "callgraph" | "qdrant"


class SandboxResult(BaseModel):
    passed: bool
    exit_code: int
    run_url: Optional[str] = None
    summary: str


class RunState(TypedDict, total=False):
    run_id: str
    issue_url: str
    repo_url: str
    repo_owner: str
    repo_name: str
    issue_title: str
    issue_body: str
    base_ref: str
    clone_path: str
    test_command: str

    triage_summary: str
    suspected_symbols: List[str]

    retrieval_hits: List[dict]

    patch_diff: str
    patch_rationale: str

    sandbox_result: Optional[dict]
    attempt: int
    max_attempts: int

    status: str
    pr_url: Optional[str]
    error: Optional[str]

    audit_log: List[dict]
