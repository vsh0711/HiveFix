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

const API_KEY_STORAGE_KEY = "hivefix_api_key";

// Never a NEXT_PUBLIC_* build-time constant — that would bake the secret into the
// public JS bundle, visible to anyone who loads the deployed dashboard. Entered
// and kept client-side only, per browser.
export function getStoredApiKey(): string {
  try {
    return localStorage.getItem(API_KEY_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

export function setStoredApiKey(key: string): void {
  try {
    if (key) localStorage.setItem(API_KEY_STORAGE_KEY, key);
    else localStorage.removeItem(API_KEY_STORAGE_KEY);
  } catch {
    // ignore — private browsing / blocked storage; the key just won't persist
  }
}

export async function startRun(issueUrl: string, testCommand: string): Promise<{ run_id: string }> {
  const apiKey = getStoredApiKey();
  const res = await fetch(`${ORCHESTRATOR_URL}/runs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
    },
    body: JSON.stringify({ issue_url: issueUrl, test_command: testCommand }),
  });
  if (res.status === 401) throw new Error("401: missing or invalid API key — set it below the form");
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
