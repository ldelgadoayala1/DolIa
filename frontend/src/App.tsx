import { useEffect, useMemo, useState } from "react";

type WordItem = { word: string; weight: number };
type GraphNode = { id: string; label: string };
type GraphEdge = { id: string; source: string; target: string; weight: number };

type FinalResult = {
  summary?: string;
  wordcloud?: WordItem[];
  graph?: { nodes: GraphNode[]; edges: GraphEdge[] };
};

export default function App() {
  const [query, setQuery] = useState<string>("resfriado común");
  const [maxResults, setMaxResults] = useState<number>(30);
  const [sources, setSources] = useState<string[]>(["reddit", "stackoverflow"]);

  const [jobId, setJobId] = useState<string>("");
  const [events, setEvents] = useState<any[]>([]);
  const [progress, setProgress] = useState<number>(0);
  const [status, setStatus] = useState<string>("Listo.");
  const [stage, setStage] = useState<string>("");

  const [result, setResult] = useState<FinalResult | null>(null);

  const apiBase = ""; // desde docker, asumimos mismo host/puertos proxy no; cambiamos si necesitas

  const normalizedSources = useMemo(() => sources, [sources]);

  const startSearch = async () => {
    setResult(null);
    setEvents([]);
    setProgress(0);
    setStage("");
    setStatus("Enviando búsqueda...");

    const resp = await fetch(`http://localhost:8000/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        sources: normalizedSources,
        max_results: maxResults,
        include_graph: true,
        include_wordcloud: true,
      }),
    });

    if (!resp.ok) {
      const txt = await resp.text();
      setStatus(`Error iniciando búsqueda: ${txt}`);
      return;
    }

    const data = await resp.json();
    setJobId(data.job_id);
    setStatus("Abriendo stream SSE...");
  };

  useEffect(() => {
    if (!jobId) return;

    const url = `http://localhost:8000/events?job_id=${encodeURIComponent(jobId)}`;
    const es = new EventSource(url);

    es.onmessage = (ev) => {
      try {
        const payload = JSON.parse(ev.data);
        setEvents((prev) => [...prev, payload]);

        if (payload.type === "done") {
          setStage(payload.stage ?? "finalize");
          setProgress(payload.progress ?? 100);
          setStatus(payload.status ?? "Completado");
          if (payload.data) setResult(payload.data as FinalResult);
          es.close();
          return;
        }

        if (payload.type === "error") {
          setStage(payload.stage ?? "error");
          setProgress(100);
          setStatus(payload.status ?? "Error");
          es.close();
          return;
        }

        setStage(payload.stage ?? "");
        setProgress(payload.progress ?? 0);
        setStatus(payload.status ?? "");
      } catch (e) {
        // ignorar mensajes no parseables
      }
    };

    es.onerror = () => {
      setStatus("Error no se pudo establecer comunicacion con el backend (SSE).");
      es.close();
    };

    return () => {
      es.close();
    };
  }, [jobId]);

  const wordcloud = result?.wordcloud ?? [];
  const graph = result?.graph;

  return (
    <div style={{ fontFamily: "sans-serif", padding: 24, maxWidth: 1100, margin: "0 auto" }}>
      <h1>WebScrappingUNAB (MVP SSE)</h1>

      <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
        {/* Sidebar */}
        <div style={{ width: 360, border: "1px solid #ddd", padding: 16, borderRadius: 8 }}>
          <h3>Buscar dolencia / tema</h3>

          <label style={{ display: "block", marginTop: 12 }}>
            <div>Query</div>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              style={{ width: "100%", padding: 8, marginTop: 6 }}
            />
          </label>

          <label style={{ display: "block", marginTop: 12 }}>
            <div>Max resultados: {maxResults}</div>
            <input
              type="range"
              min={1}
              max={200}
              value={maxResults}
              onChange={(e) => setMaxResults(Number(e.target.value))}
              style={{ width: "100%", marginTop: 6 }}
            />
          </label>

          <div style={{ marginTop: 12 }}>
            <div>Fuentes</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
              {["reddit", "stackoverflow"].map((s) => {
                const checked = sources.includes(s);
                return (
                  <label key={s} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => {
                        setSources((prev) => {
                          if (prev.includes(s)) return prev.filter((x) => x !== s);
                          return [...prev, s];
                        });
                      }}
                    />
                    {s}
                  </label>
                );
              })}
            </div>
          </div>

          <button
            onClick={startSearch}
            style={{
              marginTop: 16,
              width: "100%",
              padding: "10px 12px",
              cursor: "pointer",
            }}
          >
            Buscar
          </button>

          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 12, color: "#666" }}>job_id</div>
            <div style={{ wordBreak: "break-all", fontFamily: "monospace" }}>{jobId || "-"}</div>
          </div>
        </div>

        {/* Main */}
        <div style={{ flex: 1 }}>
          <div style={{ border: "1px solid #ddd", padding: 16, borderRadius: 8 }}>
            <h3>Progreso</h3>

            <div style={{ marginTop: 8 }}>
              <div>
                <b>Stage:</b> {stage || "-"}
              </div>
              <div>
                <b>Status:</b> {status}
              </div>
              <div style={{ marginTop: 10, background: "#f1f1f1", borderRadius: 8, height: 14 }}>
                <div
                  style={{
                    width: `${progress}%`,
                    height: "100%",
                    background: "#4f46e5",
                    borderRadius: 8,
                    transition: "width 200ms",
                  }}
                />
              </div>
              <div style={{ marginTop: 6, fontSize: 12, color: "#666" }}>{progress}%</div>
            </div>
          </div>

          <div style={{ marginTop: 16, border: "1px solid #ddd", padding: 16, borderRadius: 8 }}>
            <h3>Resultados</h3>
            {!result ? (
              <p>Inicia una búsqueda para ver nube de palabras y grafo.</p>
            ) : (
              <>
                {result.summary && <p><b>Resumen:</b> {result.summary}</p>}

                {/* Wordcloud (MVP HTML) */}
                <h4>Nube de palabras (MVP)</h4>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  {wordcloud.map((w) => (
                    <span
                      key={w.word}
                      style={{
                        fontSize: `${Math.max(12, Math.min(42, 10 + w.weight))}px`,
                        background: "#eef2ff",
                        padding: "4px 10px",
                        borderRadius: 999,
                      }}
                    >
                      {w.word}
                    </span>
                  ))}
                </div>

                {/* Graph (MVP HTML) */}
                <h4 style={{ marginTop: 18 }}>Grafo (MVP)</h4>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <div>
                    <div style={{ fontWeight: 600, marginBottom: 8 }}>Nodes</div>
                    <pre
                      style={{
                        background: "#f8fafc",
                        padding: 12,
                        borderRadius: 8,
                        maxHeight: 240,
                        overflow: "auto",
                      }}
                    >
                      {JSON.stringify(graph?.nodes ?? [], null, 2)}
                    </pre>
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, marginBottom: 8 }}>Edges</div>
                    <pre
                      style={{
                        background: "#f8fafc",
                        padding: 12,
                        borderRadius: 8,
                        maxHeight: 240,
                        overflow: "auto",
                      }}
                    >
                      {JSON.stringify(graph?.edges ?? [], null, 2)}
                    </pre>
                  </div>
                </div>
              </>
            )}
          </div>

          <div style={{ marginTop: 16, border: "1px solid #ddd", padding: 16, borderRadius: 8 }}>
            <h3>Eventos (debug)</h3>
            <pre style={{ background: "#111827", color: "#e5e7eb", padding: 12, borderRadius: 8, overflow: "auto", maxHeight: 220 }}>
              {JSON.stringify(events, null, 2)}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}