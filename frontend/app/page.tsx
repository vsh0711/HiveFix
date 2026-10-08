import Link from "next/link";
import { PixelBee } from "@/components/PixelBee";
import { RunForm } from "@/components/RunForm";
import { listRuns } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const runs = await listRuns().catch(() => []);

  return (
    <main className="max-w-3xl mx-auto px-4 py-10 flex flex-col gap-8">
      <header className="flex items-center gap-4">
        <PixelBee />
        <div>
          <h1 className="text-hive-amber text-lg">HiveFix</h1>
          <p className="text-[10px] text-hive-line mt-2">Buzz turns issues into merge-ready PRs.</p>
        </div>
      </header>

      <RunForm />

      <section>
        <h2 className="text-hive-amber text-[11px] mb-3">Recent runs</h2>
        <div className="flex flex-col gap-2">
          {runs.length === 0 && <p className="text-[10px] text-hive-line">No runs yet.</p>}
          {runs.map((run) => (
            <Link
              key={run.run_id}
              href={`/runs/${run.run_id}`}
              className="pixel-border bg-hive-panel p-3 flex justify-between items-center text-[10px] hover:bg-hive-line"
            >
              <span className="truncate max-w-[60%]">{run.issue_url}</span>
              <StatusBadge status={run.status} />
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    resolved: "bg-hive-mint text-hive-ink",
    failed: "bg-hive-danger text-hive-ink",
  };
  return (
    <span className={`px-2 py-1 pixel-border ${colors[status] || "bg-hive-amber text-hive-ink"}`}>
      {status}
    </span>
  );
}
