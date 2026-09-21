// frontend/src/components/HistoryPanel.tsx
import { Fragment, useEffect, useState } from "react";

type ProviderRow = {
  slug: string;
  display_name: string;
  status: string;
  description: string | null;
  rate_limit_info: string | null;
  requires_auth: boolean;
};

type HistoryItem = {
  job_id: string;
  query: string;
  sources: string[];
  max_results: number;
  status: string;
  summary: string | null;
  posts_count: number | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
};

type JobLogItem = {
  stage: string;
  level: string;
  message: string;
  data: unknown;
  created_at: string;
};

const STATUS_LABEL: Record<string, string> = {
  queued: "En cola",
  running: "En curso",
  done: "Completado",
  error: "Error",
};

const PROVIDER_STATUS_LABEL: Record<string, string> = {
  active: "Activa",
  pending: "Pendiente",
  blocked: "Bloqueada",
};

function formatDate(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("es-CL");
}

const API_BASE = "http://localhost:8000";

export default function HistoryPanel() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [providers, setProviders] = useState<ProviderRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const [logsByJob, setLogsByJob] = useState<Record<string, JobLogItem[]>>({});
  const [logsLoadingJobId, setLogsLoadingJobId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [historyResp, providersResp] = await Promise.all([
          fetch(`${API_BASE}/search_history?limit=50`),
          fetch(`${API_BASE}/providers`),
        ]);

        if (!historyResp.ok || !providersResp.ok) {
          throw new Error("request failed");
        }

        const historyData = await historyResp.json();
        const providersData = await providersResp.json();

        if (!cancelled) {
          setItems(historyData.items ?? []);
          setProviders(providersData ?? []);
        }
      } catch {
        if (!cancelled) setError("No se pudo cargar el historial. Verifica que el backend esté activo.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const toggleLogs = async (jobId: string) => {
    if (expandedJobId === jobId) {
      setExpandedJobId(null);
      return;
    }
    setExpandedJobId(jobId);

    if (!logsByJob[jobId]) {
      setLogsLoadingJobId(jobId);
      try {
        const resp = await fetch(`${API_BASE}/search_history/${jobId}/logs`);
        if (resp.ok) {
          const data = await resp.json();
          setLogsByJob((prev) => ({ ...prev, [jobId]: data.logs ?? [] }));
        }
      } finally {
        setLogsLoadingJobId(null);
      }
    }
  };

  if (loading) {
    return <p className="status-text">Cargando historial...</p>;
  }

  if (error) {
    return <p className="status-text">{error}</p>;
  }

  return (
    <div>
      {providers.length > 0 && (
        <section className="result-card">
          <h2 className="result-card-title">🧩 Fuentes registradas</h2>
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Fuente</th>
                  <th>Estado</th>
                  <th>Descripción</th>
                  <th>Rate limit</th>
                  <th>Requiere auth</th>
                </tr>
              </thead>
              <tbody>
                {providers.map((p) => (
                  <tr key={p.slug}>
                    <td>{p.display_name}</td>
                    <td>{PROVIDER_STATUS_LABEL[p.status] ?? p.status}</td>
                    <td>{p.description ?? "-"}</td>
                    <td>{p.rate_limit_info ?? "-"}</td>
                    <td>{p.requires_auth ? "Sí" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="result-card">
        <h2 className="result-card-title">🕓 Historial de búsquedas</h2>

        {items.length === 0 ? (
          <p className="status-text">Todavía no hay búsquedas registradas.</p>
        ) : (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Query</th>
                  <th>Fuentes</th>
                  <th className="numeric">Máx.</th>
                  <th>Estado</th>
                  <th className="numeric">Posts</th>
                  <th>Creado</th>
                  <th>Completado</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <Fragment key={item.job_id}>
                    <tr>
                      <td>{item.query}</td>
                      <td>{item.sources.join(", ")}</td>
                      <td className="numeric">{item.max_results}</td>
                      <td>{STATUS_LABEL[item.status] ?? item.status}</td>
                      <td className="numeric">{item.posts_count ?? "-"}</td>
                      <td>{formatDate(item.created_at)}</td>
                      <td>{formatDate(item.completed_at)}</td>
                      <td>
                        <button className="data-table-clear" onClick={() => toggleLogs(item.job_id)}>
                          {expandedJobId === item.job_id ? "Ocultar logs" : "Ver logs"}
                        </button>
                      </td>
                    </tr>
                    {expandedJobId === item.job_id && (
                      <tr>
                        <td colSpan={8}>
                          {item.error_message && (
                            <p className="status-text">⚠️ {item.error_message}</p>
                          )}
                          {logsLoadingJobId === item.job_id ? (
                            <p className="status-text">Cargando logs...</p>
                          ) : (logsByJob[item.job_id]?.length ?? 0) === 0 ? (
                            <p className="status-text">Sin logs registrados para este job.</p>
                          ) : (
                            <ul className="history-log-list">
                              {logsByJob[item.job_id].map((log, i) => (
                                <li key={i}>
                                  <strong>[{log.stage}]</strong> {log.level} — {log.message}{" "}
                                  <span className="status-text">({formatDate(log.created_at)})</span>
                                </li>
                              ))}
                            </ul>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
