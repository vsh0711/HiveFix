export const ORCHESTRATOR_URL =
  process.env.NEXT_PUBLIC_ORCHESTRATOR_URL || "http://localhost:8000";

export type RunState = {
  run_id: string;
  issue_url: string;
  repo_url?: string;
  issue_title?: string;
  triage_summary?: string;
  retrieval_hits?: { file_path: string; symbol?: string; score: number; snippet: string; source: string }[];
  patch_diff?: string;
  patch_rationale?: string;
  sandbox_result?: { passed: boolean; conclusion: string; run_url?: string; summary: string };
  attempt?: number;
  status: string;
  pr_url?: string;
  error?: string;
  audit_log?: { ts: number; identity: string; action: string; status: string; detail: Record<string, unknown> }[];
};

export async function startRun(issueUrl: string, testCommand: string): Promise<{ run_id: string }> {
  const res = await fetch(`${ORCHESTRATOR_URL}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ issue_url: issueUrl, test_command: testCommand }),
  });
  if (!res.ok) throw new Error(`Failed to start run: ${res.status}`);
  return res.json();
}

export async function listRuns(): Promise<RunState[]> {
  const res = await fetch(`${ORCHESTRATOR_URL}/runs`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to list runs: ${res.status}`);
  return res.json();
}

export async function getRun(runId: string): Promise<RunState> {
  const res = await fetch(`${ORCHESTRATOR_URL}/runs/${runId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to get run: ${res.status}`);
  return res.json();
}

export function subscribeToRun(runId: string, onUpdate: (state: RunState) => void): () => void {
  const source = new EventSource(`${ORCHESTRATOR_URL}/runs/${runId}/events`);
  source.onmessage = (event) => {
    try {
      onUpdate(JSON.parse(event.data));
    } catch {
      // ignore malformed/keep-alive frames
    }
  };
  return () => source.close();
}
