import { PixelBee } from "./PixelBee";

const STAGES = [
  { key: "triaged", label: "Scout", hint: "reading the issue" },
  { key: "retrieved", label: "Trail", hint: "following BM25 + call-graph hits" },
  { key: "patched", label: "Pollinate", hint: "drafting the fix" },
  { key: "tested", label: "Hive-check", hint: "sandboxed regression run" },
  { key: "resolved", label: "Honey", hint: "PR opened" },
] as const;

const ORDER = ["queued", "triaged", "retrieved", "patched", "tested", "resolved", "failed"];

export function StageStepper({ status }: { status: string }) {
  const currentIndex = ORDER.indexOf(status);
  const failed = status === "failed";

  return (
    <div className="flex items-center gap-2 overflow-x-auto py-6">
      {STAGES.map((stage, i) => {
        const stageIndex = ORDER.indexOf(stage.key);
        const reached = currentIndex >= stageIndex;
        const active = currentIndex === stageIndex;
        return (
          <div key={stage.key} className="flex items-center gap-2">
            <div
              className={`pixel-border flex flex-col items-center justify-center w-24 h-24 shrink-0 ${
                failed && !reached
                  ? "bg-hive-panel opacity-40"
                  : reached
                  ? "bg-hive-amber text-hive-ink"
                  : "bg-hive-panel text-hive-amber opacity-60"
              }`}
            >
              {active && !failed ? <PixelBee animate /> : <PixelBee animate={false} className="opacity-70" />}
              <span className="text-[9px] mt-1 text-center leading-tight">{stage.label}</span>
            </div>
            {i < STAGES.length - 1 && (
              <div className={`h-1 w-6 ${reached ? "bg-hive-amber" : "bg-hive-line"}`} />
            )}
          </div>
        );
      })}
      {failed && (
        <span className="ml-4 text-hive-danger text-[10px] pixel-border bg-hive-panel px-2 py-1">
          run failed
        </span>
      )}
    </div>
  );
}
