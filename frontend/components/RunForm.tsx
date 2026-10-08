"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { startRun } from "@/lib/api";

export function RunForm() {
  const [issueUrl, setIssueUrl] = useState("");
  const [testCommand, setTestCommand] = useState("pytest -q");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const { run_id } = await startRun(issueUrl, testCommand);
      router.push(`/runs/${run_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start run");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="pixel-border bg-hive-panel p-6 flex flex-col gap-4">
      <label className="text-[10px] text-hive-amber">
        GitHub issue URL
        <input
          required
          value={issueUrl}
          onChange={(e) => setIssueUrl(e.target.value)}
          placeholder="https://github.com/owner/repo/issues/123"
          className="mt-2 w-full bg-hive-ink text-hive-amber text-[10px] p-3 pixel-border outline-none"
        />
      </label>
      <label className="text-[10px] text-hive-amber">
        Test command
        <input
          value={testCommand}
          onChange={(e) => setTestCommand(e.target.value)}
          className="mt-2 w-full bg-hive-ink text-hive-amber text-[10px] p-3 pixel-border outline-none"
        />
      </label>
      <button
        type="submit"
        disabled={submitting}
        className="pixel-border bg-hive-amber text-hive-ink text-[10px] py-3 hover:bg-hive-honey disabled:opacity-50"
      >
        {submitting ? "Sending Buzz..." : "Send Buzz after it"}
      </button>
      {error && <p className="text-hive-danger text-[10px]">{error}</p>}
    </form>
  );
}
