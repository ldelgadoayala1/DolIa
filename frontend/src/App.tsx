// frontend/src/App.tsx
import { useEffect, useState } from "react";
import "../css/index.css";
import "../css/App.css";
import WordCloud from "./components/WordCloud";
import SearchPipeline from "./components/SearchPipeline";
import DataTable, { type PostRow } from "./components/DataTable";
import HistoryPanel from "./components/HistoryPanel";

// ✅ Tipos alineados con lo que devuelve el backend
type WordItem = { text: string; value: number };

type FinalResult = {
  summary?: string;
  wordcloud?: WordItem[];
  posts?: PostRow[];
};

// Fuentes que la página tiene implementadas — la búsqueda siempre consulta
// todas, sin selección manual del usuario.
const SOURCES = ["stackoverflow", "github", "hackernews", "rss", "crossref"];

// Cantidad fija de resultados por búsqueda (sin selector en la UI).
const MAX_RESULTS = 10;

export default function App() {
  const [query,      setQuery]      = useState<string>("");
  const [jobId,    setJobId]      = useState<string>("");
  const [events,     setEvents]     = useState<any[]>([]);
  const [progress,   setProgress]   = useState<number>(0);
  const [status,     setStatus]     = useState<string>("Listo para buscar.");
  const [stage,      setStage]      = useState<string>("");
  const [result,     setResult]     = useState<FinalResult | null>(null);
  const [loading,    setLoading]    = useState<boolean>(false);
  const [hasError,   setHasError]   = useState<boolean>(false);
  const [showDebug,  setShowDebug]  = useState<boolean>(false);
  const [stageCounts, setStageCounts] = useState<Record<string, number>>({});
  const [view, setView] = useState<"search" | "history">("search");

  const apiSearchUrl  = "http://localhost:8000/search";
  const apiEventsBase = "http://localhost:8000/events";

  // ── Iniciar búsqueda ──────────────────────────────────────────
  const startSearch = async () => {
    setResult(null);
    setEvents([]);
    setProgress(0);
    setStage("");
    setHasError(false);
    setStageCounts({});
    setLoading(true);
    setStatus("Enviando búsqueda...");

    try {
      const resp = await fetch(apiSearchUrl, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          sources:           SOURCES,
          max_results:       MAX_RESULTS,
          include_graph:     false,
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

          if (Array.isArray(payload.data?.posts)) {
            setStageCounts((prev) => ({
              ...prev,
              finalize: payload.data.posts.length,
            }));
          }

          // ✅ Normalizar datos del resultado
          if (payload.data) {
            const raw = payload.data;

            const wordcloud: WordItem[] = (raw.wordcloud ?? []).map(
              (w: any) => ({
                text:  w.text  ?? w.word  ?? "",
                value: w.value ?? w.weight ?? 1,
              })
            );

            const posts: PostRow[] = (raw.posts ?? []).map((p: any) => ({
              title: String(p.title ?? "Sin título"),
              url: String(p.url ?? "#"),
              source: String(p.source ?? "StackOverflow"),
              score: Number(p.score ?? 0),
              date: String(p.date ?? "-"),
              author: String(p.author ?? "-"),
              relevanceScore:
                p.relevance_score === null || p.relevance_score === undefined
                  ? null
                  : Number(p.relevance_score),
              tag: String(p.tag ?? "-"),
            }));

            setResult({
              summary:   raw.summary ?? "",
              wordcloud,
              posts,
            });
          }

          setLoading(false);
          es.close();
          return;
        }

        if (payload.type === "error") {
          setHasError(true);
          setProgress(100);
          setStatus(payload.status ?? "Error en el proceso");
          setLoading(false);
          es.close();
          return;
        }

        setStage(payload.stage    ?? "");
        setProgress(payload.progress ?? 0);
        setStatus(payload.status  ?? "");

        if (typeof payload.data?.count === "number" && payload.stage) {
          const stageKey = payload.stage;
          setStageCounts((prev) => ({ ...prev, [stageKey]: payload.data.count }));
        }

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
  const isDone    = stage === "finalize" || (progress === 100 && !loading);
  const isError   = hasError;

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
        <div className="navbar-tabs">
          <button
            className={`navbar-tab ${view === "search" ? "navbar-tab-active" : ""}`}
            onClick={() => setView("search")}
          >
            Buscar
          </button>
          <button
            className={`navbar-tab ${view === "history" ? "navbar-tab-active" : ""}`}
            onClick={() => setView("history")}
          >
            Historial
          </button>
        </div>
        <div className="navbar-badge">MVP SSE</div>
      </nav>

      {/* ── LAYOUT ── */}
      <div className="app-layout">

        {view === "search" && (
          <>
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
                    placeholder="Ej: SQL injection"
                    onKeyDown={(e) => e.key === "Enter" && startSearch()}
                  />
                </div>

                {/* Botón buscar */}
                <button
                  className="btn-search"
                  onClick={startSearch}
                  disabled={loading}
                >
                  {loading ? "⏳ Buscando..." : "🔍 Buscar"}
                </button>
              </div>

              {/* ── Pipeline + Estado (animación de carga unificada) ── */}
              <div className="sidebar-card">
                <div className="sidebar-card-title">🚀 Progreso</div>
                <SearchPipeline
                  stage={stage}
                  progress={progress}
                  status={status}
                  loading={loading}
                  isError={isError}
                  counts={stageCounts}
                />
              </div>
            </aside>

            {/* ════ MAIN CONTENT ════ */}
            <main className="app-main">

              {/* ── WordCloud ── */}
              {wordcloud.length > 0 && (
                <section className="result-card">
                  <h2 className="result-card-title">☁️ Nube de Palabras</h2>
                  <WordCloud words={wordcloud} />
                </section>
              )}

              {/* ── DataTable ── */}
              {result?.posts && (
                <section className="result-card">
                  <h2 className="result-card-title">📋 Resultados</h2>
                  {result.posts.length > 0 ? (
                    <DataTable posts={result.posts} />
                  ) : (
                    <p className="status-text">
                      No se encontraron resultados respecto a la búsqueda actual.
                    </p>
                  )}
                </section>
              )}

              {/* ── Estado vacío ── */}
              {!loading && !result && (
                <div className="empty-state">
                  <div className="empty-icon">🔬</div>
                  <h3>Ingresa una dolencia para comenzar</h3>
                  <p>
                    El sistema analizará publicaciones de múltiples fuentes que aporten información relevante para su investigación
                  </p>
                </div>
              )}

            </main>
          </>
        )}

        {view === "history" && (
          <main className="app-main" style={{ width: "100%" }}>
            <HistoryPanel />
          </main>
        )}
      </div>
    </div>
  );
}