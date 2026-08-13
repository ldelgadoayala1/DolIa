// frontend/src/App.tsx
import { useEffect, useMemo, useState } from "react";
import "../css/index.css";
import "../css/App.css";
import WordCloud from "./components/WordCloud";
import GraphView from "./components/GraphView";
import SearchPipeline from "./components/SearchPipeline";
import DataTable, { type PostRow } from "./components/DataTable";

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
  relation?: string;
};

type FinalResult = {
  summary?: string;
  wordcloud?: WordItem[];
  graph?: { nodes: GraphNode[]; edges: GraphEdge[] };
  posts?: PostRow[];
};

const SOURCE_ICONS: Record<string, string> = {
  stackoverflow: "🟡",
};

const AVAILABLE_SOURCES = ["stackoverflow"];

export default function App() {
  const [query,      setQuery]      = useState<string>("");
  const [maxResults, setMaxResults] = useState<number>(30);
  const [sources,    setSources]    = useState<string[]>(["stackoverflow"]);
  const [jobId,      setJobId]      = useState<string>("");
  const [events,     setEvents]     = useState<any[]>([]);
  const [progress,   setProgress]   = useState<number>(0);
  const [status,     setStatus]     = useState<string>("Listo para buscar.");
  const [stage,      setStage]      = useState<string>("");
  const [result,     setResult]     = useState<FinalResult | null>(null);
  const [loading,    setLoading]    = useState<boolean>(false);
  const [hasError,   setHasError]   = useState<boolean>(false);
  const [showDebug,  setShowDebug]  = useState<boolean>(false);
  const [stageCounts, setStageCounts] = useState<Record<string, number>>({});

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

            const nodes: GraphNode[] = (raw.graph?.nodes ?? []).map(
              (n: any) => ({
                id:     String(n.id ?? n.node_id ?? ""),
                label:  String(n.label ?? n.name ?? n.id ?? ""),
                weight: Number(n.weight ?? n.frequency ?? 1),
                group:  String(n.group ?? n.community ?? "0"),
              })
            );

            const edges: GraphEdge[] = (raw.graph?.edges ?? []).map(
              (e: any, i: number) => ({
                id:       e.id ?? `edge_${i}`,
                source:   String(e.source ?? e.from ?? ""),
                target:   String(e.target ?? e.to   ?? ""),
                weight:   Number(e.weight ?? 1),
                relation: e.relation ? String(e.relation) : undefined,
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
              graph: nodes.length > 0 ? { nodes, edges } : undefined,
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
  const graph     = result?.graph;
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
                placeholder="Ej: SQL injection"
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

            {/* ✅ Fuentes — Solo StackOverflow */}
            <div className="form-group">
              <label className="form-label">Fuentes</label>
              <div className="sources-grid">
                {AVAILABLE_SOURCES.map((s) => {
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
                      <span>{SOURCE_ICONS[s]}</span>
                      <span style={{ textTransform: "capitalize" }}>{s}</span>
                    </label>
                  );
                })}
              </div>
              {/* ✅ Nota futura */}
              <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.4rem" }}>
                🔜 Más fuentes próximamente
              </p>
            </div>

            {/* Botón buscar */}
            <button
              className="btn-search"
              onClick={startSearch}
              disabled={loading || sources.length === 0}
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

          {/* ── Grafo ── */}
          {graph && (
            <section className="result-card">
              <h2 className="result-card-title">🕸️ Grafo de Relaciones</h2>
              <GraphView data={graph} />
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
                El sistema analizará publicaciones de StackOverflow
                y generará visualizaciones con IA.
              </p>
            </div>
          )}


        </main>
      </div>
    </div>
  );
}