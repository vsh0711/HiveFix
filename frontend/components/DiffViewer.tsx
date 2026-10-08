export function DiffViewer({ diff }: { diff: string }) {
  if (!diff) return null;
  const lines = diff.split("\n");
  return (
    <pre className="pixel-border bg-hive-ink p-4 text-[10px] overflow-x-auto leading-relaxed">
      {lines.map((line, i) => {
        let color = "text-hive-amber";
        if (line.startsWith("+") && !line.startsWith("+++")) color = "text-hive-mint";
        else if (line.startsWith("-") && !line.startsWith("---")) color = "text-hive-danger";
        else if (line.startsWith("@@")) color = "text-hive-honey";
        return (
          <div key={i} className={color}>
            {line || " "}
          </div>
        );
      })}
    </pre>
  );
}
