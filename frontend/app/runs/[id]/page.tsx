"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { PixelBee } from "@/components/PixelBee";
import { StageStepper } from "@/components/StageStepper";
import { DiffViewer } from "@/components/DiffViewer";
import { getRun, subscribeToRun, RunState } from "@/lib/api";

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const [run, setRun] = useState<RunState | null>(null);

  useEffect(() => {
    getRun(runId).then(setRun).catch(() => {});
    const unsubscribe = subscribeToRun(runId, setRun);
    return unsubscribe;
  }, [runId]);

  if (!run) {
    return (
      <main className="max-w-3xl mx-auto px-4 py-10">
        <p className="text-[10px] text-hive-amber">Waking Buzz up...</p>
      </main>
    );
  }

  return (
    <main className="max-w-3xl mx-auto px-4 py-10 flex flex-col gap-6">
      <Link href="/" className="text-hive-amber text-[10px]">
        &lt; back to hive
      </Link>

      <header className="flex items-center gap-3">
        <PixelBee animate={!["resolved", "failed"].includes(run.status)} />
        <div>
          <h1 className="text-hive-amber text-[12px]">{run.issue_title || run.issue_url}</h1>
          <p className="text-[9px] text-hive-line mt-1">{run.issue_url}</p>
        </div>
      </header>

      <StageStepper status={run.status} />

      {run.triage_summary && (
        <section className="pixel-border bg-hive-panel p-4">
          <h2 className="text-hive-honey text-[10px] mb-2">Scout report</h2>
          <p className="text-[10px] leading-relaxed">{run.triage_summary}</p>
        </section>
      )}

      {run.retrieval_hits && run.retrieval_hits.length > 0 && (
        <section className="pixel-border bg-hive-panel p-4">
          <h2 className="text-hive-honey text-[10px] mb-2">Trail followed</h2>
          <ul className="text-[9px] flex flex-col gap-1">
            {run.retrieval_hits.map((hit, i) => (
              <li key={i} className="flex justify-between">
                <span>
                  {hit.file_path} {hit.symbol ? `:: ${hit.symbol}` : ""}
                </span>
                <span className="text-hive-line">{hit.source}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {run.patch_diff && (
        <section>
          <h2 className="text-hive-honey text-[10px] mb-2">
            Pollinated fix {run.attempt ? `(attempt ${run.attempt})` : ""}
          </h2>
          <DiffViewer diff={run.patch_diff} />
        </section>
      )}

      {run.sandbox_result && (
        <section
          className={`pixel-border p-4 ${
            run.sandbox_result.passed ? "bg-hive-mint text-hive-ink" : "bg-hive-danger text-hive-ink"
          }`}
        >
          <h2 className="text-[10px] mb-2">Hive-check</h2>
          <p className="text-[10px]">{run.sandbox_result.summary}</p>
          {run.sandbox_result.run_url && (
            <a href={run.sandbox_result.run_url} target="_blank" className="text-[9px] underline">
              view sandbox run logs
            </a>
          )}
        </section>
      )}

      {run.pr_url && (
        <section className="pixel-border bg-hive-amber text-hive-ink p-4">
          <h2 className="text-[10px] mb-2">Honey delivered</h2>
          <a href={run.pr_url} target="_blank" className="text-[10px] underline">
            {run.pr_url}
          </a>
        </section>
      )}

      {run.error && (
        <section className="pixel-border bg-hive-danger text-hive-ink p-4 text-[10px]">{run.error}</section>
      )}

      {run.audit_log && run.audit_log.length > 0 && (
        <section className="pixel-border bg-hive-panel p-4">
          <h2 className="text-hive-honey text-[10px] mb-3">Audit trail</h2>
          <ul className="text-[9px] flex flex-col gap-2">
            {run.audit_log.map((e, i) => (
              <li key={i} className="flex flex-col border-b border-hive-line pb-2 last:border-0">
                <span className="flex justify-between">
                  <span className="text-hive-amber">{e.identity}</span>
                  <span className={e.status === "ok" ? "text-hive-mint" : "text-hive-danger"}>{e.status}</span>
                </span>
                <span>{e.action}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
