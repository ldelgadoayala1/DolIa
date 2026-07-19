import { useEffect, useMemo, useState } from "react";

import "../css/index.css";
import "../css/App.css";
import WordCloud from "./components/WordCloud";
import GraphView from "./components/GraphView";

type WordItem  = { word: string; weight: number };
type GraphNode = { id: string; label: string };
type GraphEdge = { id?: string; source: string; target: string; weight?: number };
type FinalResult = {
  summary?:   string;
  wordcloud?: WordItem[];
  graph?:     { nodes: GraphNode[]; edges: GraphEdge[] };
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

  /* ── Rango visual del slider ── */
  const rangePct = `${((maxResults - 1) / 199) * 100}%`;

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
          sources:          normalizedSources,
          max_results:      maxResults,
          include_graph:    true,
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
      setStatus("Error no se pudo establecer comunicacion con el backend.");
      setLoading(false);
    }
  };

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
          if (payload.data) setResult(payload.data as FinalResult);
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

        setStage(payload.stage   ?? "");
        setProgress(payload.progress ?? 0);
        setStatus(payload.status ?? "");
      } catch (_) { /* ignorar */ }
    };

    es.onerror = () => {
      setStatus("Error no se pudo establecer comunicacion con el LLM");
      setLoading(false);
      es.close();
    };

    return () => { es.close(); };
  }, [jobId]);

  const wordcloud = result?.wordcloud ?? [];
  const graph     = result?.graph;
  const isDone    = stage === "finalize" || (progress === 100 && !loading);
  const isError   = stage === "error";

  const getStageState = (s: string) => {
    if (isError && s === "error") return "error";
    const idx        = STAGES.indexOf(stage);
    const sIdx       = STAGES.indexOf(s);
    if (sIdx < idx)  return "done";
    if (sIdx === idx) return "active";
    return "";
  };

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
            <div className="sidebar-card-title">
              🔍 Búsqueda
            </div>

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

            {/* Botón */}
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

          {/* ── Progreso ── */}
          <div className="main-card">
            <div className="main-card-header">
              <div className="main-card-title">Pipeline de análisis</div>
            </div>

            {/* Etapas */}
            <div className="progress-stages">
              {STAGES.map((s) => (
                <span
                  key={s}
                  className={`stage-pill ${getStageState(s)}`}
                >
                  {STAGE_LABELS[s] ?? s}
                </span>
              ))}
            </div>

            {/* Info */}
            <div className="progress-info">
              <span className="progress-status">{status}</span>
              <span className="progress-pct">{progress}%</span>
            </div>

            {/* Barra */}
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
                  Aún no hay resultados
                </div>
                <div className="results-empty-sub">
                  Ingresa un término y presiona <strong>Buscar</strong> para comenzar
                </div>
              </div>
            ) : (
              <div className="fade-in-up">
                {result.summary && (
                  <div className="summary-box">
                    <div className="summary-label">Resumen IA</div>
                    {result.summary}
                  </div>
                )}
                <div className="viz-grid">
                  <div className="viz-panel">
                    <div className="viz-panel-title">☁️ Nube de palabras</div>
                    <WordCloud wordcloud={wordcloud} />
                  </div>
                  <div className="viz-panel">
                    <div className="viz-panel-title">🕸️ Grafo de relaciones</div>
                    <GraphView graph={graph} height={480} />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* ── Debug ── */}
          <div className="main-card debug-card">
            <div className="main-card-header">
              <div className="main-card-title">Eventos SSE</div>
              <button
                className="debug-toggle"
                onClick={() => setShowDebug((v) => !v)}
              >
                {showDebug ? "Ocultar" : "Mostrar"} ({events.length})
              </button>
            </div>
            {showDebug && (
              <pre className="debug-pre">
                {JSON.stringify(events, null, 2)}
              </pre>
            )}
          </div>

        </main>
      </div>

      {/* ── FOOTER ── */}
      <footer className="app-footer">
        <strong>DolIA</strong> — Proyecto de Investigación ·{" "}
        Universidad Andrés Bello · {new Date().getFullYear()}
      </footer>
    </div>
  );
}