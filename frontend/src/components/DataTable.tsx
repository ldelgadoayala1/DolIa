// frontend/src/components/DataTable.tsx
import { useMemo, useState } from "react";

export type PostRow = {
  title: string;
  url: string;
  source: string;
  score: number;
  date: string;
  author: string;
  relevanceScore: number | null;
  tag: string;
};

type Props = {
  posts: PostRow[];
};

type SortKey = "title" | "source" | "score" | "relevanceScore" | "tag" | "date" | "author";
type SortDir = "asc" | "desc";

const COLUMNS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: "title",          label: "Título" },
  { key: "source",         label: "Fuente" },
  { key: "score",          label: "Score", numeric: true },
  { key: "relevanceScore", label: "Relevancia", numeric: true },
  { key: "tag",            label: "Etiqueta" },
  { key: "date",           label: "Fecha" },
  { key: "author",         label: "Autor" },
];

export default function DataTable({ posts }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("relevanceScore");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [search,  setSearch]  = useState("");
  const [tagFilter, setTagFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");

  const tags = useMemo(
    () => Array.from(new Set(posts.map((p) => p.tag).filter(Boolean))).sort(),
    [posts]
  );
  const sources = useMemo(
    () => Array.from(new Set(posts.map((p) => p.source).filter(Boolean))).sort(),
    [posts]
  );

  const hasActiveFilters = search.trim() !== "" || tagFilter !== "all" || sourceFilter !== "all";

  const clearFilters = () => {
    setSearch("");
    setTagFilter("all");
    setSourceFilter("all");
  };

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return posts.filter((p) => {
      if (tagFilter !== "all" && p.tag !== tagFilter) return false;
      if (sourceFilter !== "all" && p.source !== sourceFilter) return false;
      if (q && !p.title.toLowerCase().includes(q) && !p.author.toLowerCase().includes(q)) {
        return false;
      }
      return true;
    });
  }, [posts, search, tagFilter, sourceFilter]);

  const sorted = useMemo(() => {
    const dir = sortDir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const va = a[sortKey];
      const vb = b[sortKey];

      if (va === null && vb === null) return 0;
      if (va === null) return 1;
      if (vb === null) return -1;

      if (typeof va === "number" && typeof vb === "number") {
        return (va - vb) * dir;
      }
      return String(va).localeCompare(String(vb)) * dir;
    });
  }, [filtered, sortKey, sortDir]);

  return (
    <div>
      <div className="data-table-toolbar">
        <input
          className="form-input data-table-search"
          placeholder="🔎 Buscar por título o autor..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />

        <select
          className="form-input data-table-select"
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value)}
        >
          <option value="all">Todas las fuentes</option>
          {sources.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>

        <select
          className="form-input data-table-select"
          value={tagFilter}
          onChange={(e) => setTagFilter(e.target.value)}
        >
          <option value="all">Todas las etiquetas</option>
          {tags.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>

        {hasActiveFilters && (
          <button className="data-table-clear" onClick={clearFilters}>
            ✕ Limpiar filtros
          </button>
        )}
      </div>

      <p className="data-table-count">
        {sorted.length} de {posts.length} resultados
      </p>

      {sorted.length > 0 ? (
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                {COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    className={`data-table-th-sortable ${col.numeric ? "numeric" : ""}`}
                    onClick={() => handleSort(col.key)}
                  >
                    {col.label}
                    <span className={`data-table-sort-icon ${sortKey === col.key ? "active" : ""}`}>
                      {sortKey === col.key ? (sortDir === "asc" ? "▲" : "▼") : "⇅"}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((post, index) => (
                <tr key={`${post.title}-${index}`}>
                  <td>
                    {post.url && post.url !== "#" ? (
                      <a
                        className="data-table-title-link"
                        href={post.url}
                        target="_blank"
                        rel="noreferrer"
                        title={post.url}
                      >
                        {post.title}
                      </a>
                    ) : (
                      post.title
                    )}
                  </td>
                  <td>{post.source}</td>
                  <td className="numeric">{post.score}</td>
                  <td className="numeric">{post.relevanceScore ?? "-"}</td>
                  <td>{post.tag}</td>
                  <td>{post.date}</td>
                  <td>{post.author}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="status-text">
          No hay resultados que coincidan con los filtros aplicados.
        </p>
      )}
    </div>
  );
}
