// frontend/src/components/SearchPipeline.tsx
type Stage = {
  key: string;
  icon: string;
  label: string;
};

const STAGES: Stage[] = [
  { key: "scraping",    icon: "🔍", label: "Scraping" },
  { key: "cleaning",    icon: "🧹", label: "Limpieza" },
  { key: "classifying", icon: "🤖", label: "IA" },
  { key: "building",    icon: "📊", label: "Gráficos" },
  { key: "finalize",    icon: "✅", label: "Listo" },
];

type StageState = "pending" | "active" | "done" | "error";

type Props = {
  stage: string;
  progress: number;
  status: string;
  loading: boolean;
  isError: boolean;
  counts?: Record<string, number>;
};

export default function SearchPipeline({ stage, progress, status, loading, isError, counts = {} }: Props) {
  const activeIdx = STAGES.findIndex((s) => s.key === stage);

  const states: StageState[] = STAGES.map((s, i) => {
    if (activeIdx === -1) return "pending";
    if (isError && i === activeIdx) return "error";
    if (i < activeIdx) return "done";
    if (i === activeIdx) return loading ? "active" : "done";
    return "pending";
  });

  const doneCount = states.filter((s) => s === "done").length;
  const activePartial = states.includes("active") ? 0.5 : 0;
  const pipelinePct =
    STAGES.length > 1
      ? Math.min(100, ((doneCount + activePartial) / (STAGES.length - 1)) * 100)
      : 0;

  return (
    <div className="search-pipeline">
      <div
        className="search-pipeline-track"
        style={{ "--pipeline-pct": `${pipelinePct}%` } as React.CSSProperties}
      >
        {STAGES.map((s, i) => (
          <div key={s.key} className={`search-pipeline-step ${states[i]}`}>
            <div className="search-pipeline-icon">
              <span className="search-pipeline-emoji">
                {states[i] === "error" ? "❌" : s.icon}
              </span>
              {states[i] === "active" && (
                <span className="search-pipeline-dots">
                  <span />
                  <span />
                  <span />
                </span>
              )}
            </div>
            <span className="search-pipeline-label">{s.label}</span>
            {counts[s.key] !== undefined && states[i] !== "pending" && (
              <span className={`search-pipeline-count ${states[i]}`}>
                {counts[s.key]}
              </span>
            )}
          </div>
        ))}
      </div>

      <div className="progress-track">
        <div
          className={`progress-fill ${
            isError ? "error" : !loading && progress >= 100 ? "complete" : ""
          }`}
          style={{ width: `${progress}%` }}
        />
      </div>
      <p className="progress-status">{status}</p>
    </div>
  );
}
