// frontend/src/App.tsx
import { useEffect, useMemo, useState } from "react";
import "../css/index.css";
import "../css/App.css";
import WordCloud from "./components/WordCloud";
import GraphView from "./components/GraphView";

// ✅ Tipos alineados con lo que devuelve el backend
type WordItem = { text: string; value: number };

type GraphNode = {
  id: string;
  label: string;
  weight?: number;
  group?: string;
};

type GraphEdge = {
  id?: string;
  source: string;
  target: string;
  weight?: number;
};

type FinalResult = {
  summary?: string;
  wordcloud?: WordItem[];
  graph?: { nodes: GraphNode[]; edges: GraphEdge[] };
};

const STAGES = ["scraping", "cleaning", "classifying", "building", "finalize"];

const STAGE_LABELS: Record<string, string> = {
  scraping:    "🔍 Scraping",
  cleaning:    "🧹 Limpieza",
  classifying: "🤖 IA",
  building:    "📊 Gráficos",
  finalize:    "✅ Listo",
  error:       "❌ Error",
};

const SOURCE_ICONS: Record<string, string> = {
  reddit:        "🟠",
  stackoverflow: "🟡",
};

export default function App() {
  const [query,      setQuery]      = useState<string>("resfriado común");
  const [maxResults, setMaxResults] = useState<number>(30);
  const [sources,    setSources]    = useState<string[]>(["reddit", "stackoverflow"]);
  const [jobId,      setJobId]      = useState<string>("");
  const [events,     setEvents]     = useState<any[]>([]);
  const [progress,   setProgress]   = useState<number>(0);
  const [status,     setStatus]     = useState<string>("Listo para buscar.");
  const [stage,      setStage]      = useState<string>("");
  const [result,     setResult]     = useState<FinalResult | null>(null);
  const [loading,    setLoading]    = useState<boolean>(false);
  const [showDebug,  setShowDebug]  = useState<boolean>(false);

  const apiSearchUrl  = "http://localhost:8000/search";
  const apiEventsBase = "http://localhost:8000/events";

  const normalizedSources = useMemo(() => sources, [sources]);
  const rangePct = `${((maxResults - 1) / 199) * 100}%`;

  // ── Iniciar búsqueda ──────────────────────────────────────────
  const startSearch = async () => {
    setResult(null);
    setEvents([]);
    setProgress(0);
    setStage("");
    setLoading(true);
    setStatus("Enviando búsqueda...");

    try {
      const resp = await fetch(apiSearchUrl, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          sources:           normalizedSources,
          max_results:       maxResults,
          include_graph:     true,
          include_wordcloud: true,
        }),
      });

      if (!resp.ok) {
        const txt = await resp.text();
        setStatus(`Error iniciando búsqueda: ${txt}`);
        setLoading(false);
        return;
      }

      const data = await resp.json();
      setJobId(data.job_id);
      setStatus("Conectando al stream...");
    } catch (err) {
      setStatus("Error: no se pudo conectar con el backend.");
      setLoading(false);
    }
  };

  // ── SSE: escuchar eventos ─────────────────────────────────────
  useEffect(() => {
    if (!jobId) return;

    const url = `${apiEventsBase}?job_id=${encodeURIComponent(jobId)}`;
    const es  = new EventSource(url);

    es.onmessage = (ev) => {
      try {
        const payload = JSON.parse(ev.data);
        setEvents((prev) => [...prev, payload]);

        if (payload.type === "done") {
          setStage(payload.stage ?? "finalize");
          setProgress(payload.progress ?? 100);
          setStatus(payload.status ?? "Completado");

          // ✅ Normalizar datos del resultado
          if (payload.data) {
            const raw = payload.data;

            // Normalizar wordcloud: acepta {text,value} o {word,weight}
            const wordcloud: WordItem[] = (raw.wordcloud ?? []).map(
              (w: any) => ({
                text:  w.text  ?? w.word  ?? "",
                value: w.value ?? w.weight ?? 1,
              })
            );

            // Normalizar nodos del grafo
            const nodes: GraphNode[] = (raw.graph?.nodes ?? []).map(
              (n: any) => ({
                id:     String(n.id ?? n.node_id ?? ""),
                label:  String(n.label ?? n.name ?? n.id ?? ""),
                weight: Number(n.weight ?? n.frequency ?? 1),
                group:  String(n.group ?? n.community ?? "0"),
              })
            );

            // Normalizar aristas del grafo
            const edges: GraphEdge[] = (raw.graph?.edges ?? []).map(
              (e: any, i: number) => ({
                id:     e.id ?? `edge_${i}`,
                source: String(e.source ?? e.from ?? ""),
                target: String(e.target ?? e.to   ?? ""),
                weight: Number(e.weight ?? 1),
              })
            );

            setResult({
              summary:   raw.summary ?? "",
              wordcloud,
              graph: nodes.length > 0 ? { nodes, edges } : undefined,
            });
          }

          setLoading(false);
          es.close();
          return;
        }

        if (payload.type === "error") {
          setStage("error");
          setProgress(100);
          setStatus(payload.status ?? "Error en el proceso");
          setLoading(false);
          es.close();
          return;
        }

        setStage(payload.stage    ?? "");
        setProgress(payload.progress ?? 0);
        setStatus(payload.status  ?? "");

      } catch (_) { /* ignorar parse errors */ }
    };

    es.onerror = () => {
      setStatus("Error de conexión con el servidor.");
      setLoading(false);
      es.close();
    };

    return () => { es.close(); };
  }, [jobId]);

  // ── Derivados ─────────────────────────────────────────────────
  const wordcloud = result?.wordcloud ?? [];
  const graph     = result?.graph;
  const isDone    = stage === "finalize" || (progress === 100 && !loading);
  const isError   = stage === "error";

  const getStageState = (s: string) => {
    if (isError && s === "error") return "error";
    const idx  = STAGES.indexOf(stage);
    const sIdx = STAGES.indexOf(s);
    if (sIdx < idx)  return "done";
    if (sIdx === idx) return "active";
    return "";
  };

  // ── Render ────────────────────────────────────────────────────
  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>

      {/* ── NAVBAR ── */}
      <nav className="app-navbar">
        <div className="navbar-brand">
          <div className="navbar-logo">🔬</div>
          <div>
            <div className="navbar-title">
              Dol<span>IA</span>
            </div>
            <div className="navbar-subtitle">Universidad Andrés Bello</div>
          </div>
        </div>
        <div className="navbar-badge">MVP SSE</div>
      </nav>

      {/* ── LAYOUT ── */}
      <div className="app-layout">

        {/* ════ SIDEBAR ════ */}
        <aside className="app-sidebar">
          <div className="sidebar-card">
            <div className="sidebar-card-title">🔍 Búsqueda</div>

            {/* Query */}
            <div className="form-group">
              <label className="form-label">Dolencia / Tema</label>
              <input
                className="form-input"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="ej: resfriado común, dolor de cabeza..."
                onKeyDown={(e) => e.key === "Enter" && startSearch()}
              />
            </div>

            {/* Max resultados */}
            <div className="form-group">
              <div className="range-header">
                <label className="form-label" style={{ margin: 0 }}>
                  Máx. resultados
                </label>
                <span className="range-value">{maxResults}</span>
              </div>
              <input
                type="range"
                className="form-range"
                min={1}
                max={200}
                value={maxResults}
                style={{ "--range-pct": rangePct } as React.CSSProperties}
                onChange={(e) => setMaxResults(Number(e.target.value))}
              />
            </div>

            {/* Fuentes */}
            <div className="form-group">
              <label className="form-label">Fuentes</label>
              <div className="sources-grid">
                {["reddit", "stackoverflow"].map((s) => {
                  const checked = sources.includes(s);
                  return (
                    <label
                      key={s}
                      className={`source-item ${checked ? "active" : ""}`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() =>
                          setSources((prev) =>
                            prev.includes(s)
                              ? prev.filter((x) => x !== s)
                              : [...prev, s]
                          )
                        }
                      />
                      <div className="source-checkbox-ui" />
                      <span className="source-icon">
                        {SOURCE_ICONS[s] ?? "🌐"}
                      </span>
                      <span className="source-label">{s}</span>
                    </label>
                  );
                })}
              </div>
            </div>

            {/* Botón buscar */}
            <button
              className="btn-search"
              onClick={startSearch}
              disabled={loading || sources.length === 0}
            >
              {loading ? "⏳ Procesando..." : "🚀 Buscar"}
            </button>

            {/* Job ID */}
            {jobId && (
              <div className="job-id-box">
                <div className="job-id-label">Job ID</div>
                <div className="job-id-value">{jobId}</div>
              </div>
            )}
          </div>
        </aside>

        {/* ════ MAIN ════ */}
        <main className="app-main">

          {/* ── Pipeline ── */}
          <div className="main-card">
            <div className="main-card-header">
              <div className="main-card-title">Pipeline de análisis</div>
            </div>

            <div className="progress-stages">
              {STAGES.map((s) => (
                <span key={s} className={`stage-pill ${getStageState(s)}`}>
                  {STAGE_LABELS[s] ?? s}
                </span>
              ))}
            </div>

            <div className="progress-info">
              <span className="progress-status">{status}</span>
              <span className="progress-pct">{progress}%</span>
            </div>

            <div className="progress-track">
              <div
                className={`progress-fill ${isDone && !isError ? "complete" : ""} ${isError ? "error" : ""}`}
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {/* ── Resultados ── */}
          <div className="main-card">
            <div className="main-card-header">
              <div className="main-card-title">Resultados</div>
            </div>

            {!result ? (
              <div className="results-empty">
                <div className="results-empty-icon">📊</div>
                <div className="results-empty-text">
                  Aún no hay resultados. Realiza una búsqueda para comenzar.
                </div>
              </div>
            ) : (
              <div className="results-content">

                {/* Resumen */}
                {result.summary && (
                  <div className="result-section">
                    <div className="result-section-title">📝 Resumen</div>
                    <div className="result-summary">{result.summary}</div>
                  </div>
                )}

                {/* Word Cloud */}
                {wordcloud.length > 0 && (
                  <div className="result-section">
                    <div className="result-section-title">
                      ☁️ Nube de palabras
                      <span className="result-badge">
                        {wordcloud.length} términos
                      </span>
                    </div>
                    <WordCloud words={wordcloud} />
                  </div>
                )}

                {/* Grafo */}
                {graph && graph.nodes.length > 0 && (
                  <div className="result-section">
                    <div className="result-section-title">
                      🔗 Grafo de relaciones
                      <span className="result-badge">
                        {graph.nodes.length} nodos · {graph.edges.length} aristas
                      </span>
                    </div>
                    <GraphView data={graph} />
                  </div>
                )}

                {/* Debug toggle */}
                <div style={{ marginTop: "16px" }}>
                  <button
                    className="btn-debug"
                    onClick={() => setShowDebug((v) => !v)}
                  >
                    {showDebug ? "🙈 Ocultar debug" : "🐛 Ver datos raw"}
                  </button>

                  {showDebug && (
                    <pre className="debug-box">
                      {JSON.stringify(result, null, 2)}
                    </pre>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* ── Log de eventos SSE ── */}
          {events.length > 0 && (
            <div className="main-card">
              <div className="main-card-header">
                <div className="main-card-title">
                  📡 Eventos SSE
                  <span className="result-badge">{events.length}</span>
                </div>
              </div>
              <div className="events-log">
                {events.map((ev, i) => (
                  <div key={i} className={`event-item ${ev.type ?? ""}`}>
                    <span className="event-stage">
                      {STAGE_LABELS[ev.stage] ?? ev.stage ?? "—"}
                    </span>
                    <span className="event-status">{ev.status ?? ""}</span>
                    <span className="event-pct">
                      {ev.progress != null ? `${ev.progress}%` : ""}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

        </main>
      </div>
    </div>
  );
}