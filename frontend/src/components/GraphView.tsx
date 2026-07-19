import React, { useEffect, useMemo, useRef } from "react";
import cytoscape, { Core, ElementDefinition } from "cytoscape";

type GraphNode = { id: string; label: string };
type GraphEdge = { id?: string; source: string; target: string; weight?: number };

type Props = {
  graph?: { nodes: GraphNode[]; edges: GraphEdge[] };
  height?: number;
};

export default function GraphView({ graph, height = 520 }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);

  const elements = useMemo(() => {
    const nodes = graph?.nodes ?? [];
    const edges = graph?.edges ?? [];

    const nodeEls: ElementDefinition[] = nodes.map((n) => ({
      data: {
        id: n.id,
        label: n.label,
      },
    }));

    const edgeEls: ElementDefinition[] = edges.map((e, idx) => ({
      data: {
        id: e.id ?? `e_${idx}`,
        source: e.source,
        target: e.target,
        weight: e.weight ?? 1,
      },
    }));

    return [...nodeEls, ...edgeEls];
  }, [graph]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    // destruir instancia anterior
    if (cyRef.current) {
      cyRef.current.destroy();
      cyRef.current = null;
    }

    const hasData = (graph?.nodes?.length ?? 0) > 0;
    if (!hasData) return;

    const cy = cytoscape({
      container: el,
      elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": (ele: any) => {
              const id = ele.data("id") as string;
              if (id.startsWith("source_")) return "#60a5fa";
              if (id.startsWith("topic_")) return "#34d399";
              return "#a78bfa";
            },
            label: "data(label)",
            "text-valign": "center",
            "text-halign": "center",
            color: "#0b1220",
            "font-size": 10,
            "font-weight": 800,
            width: 30,
            height: 30,
            "overlay-opacity": 0,
            "text-wrap": "wrap",
            "text-max-width": 90,
          },
        },
        {
          selector: "edge",
          style: {
            width: (ele: any) => {
              const w = ele.data("weight") ?? 1;
              return Math.max(1, Math.min(8, w));
            },
            "line-color": "#94a3b8",
            opacity: 0.75,
            "curve-style": "bezier",
            "target-arrow-shape": "triangle",
            "target-arrow-color": "#94a3b8",
          },
        },
        {
          selector: ":selected",
          style: {
            "border-width": 2,
            "border-color": "#fbbf24",
          },
        },
      ],
      layout: {
        name: "cose",
        animate: false,
        randomize: false, // ✅ antes true
        padding: 10,
    },
      userPanningEnabled: true,
      userZoomingEnabled: true,
      minZoom: 0.3,
      maxZoom: 2.5,
    });

    // debug al click (opcional)
    cy.on("tap", "node", (evt) => {
      const node = evt.target;
      const label = node.data("label");
      console.log("Nodo:", label);
    });

    cyRef.current = cy;

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [elements]);

  const hasData = (graph?.nodes?.length ?? 0) > 0;

  return (
    <div style={{ width: "100%" }}>
      <div style={{ fontWeight: 700, marginBottom: 8 }}>Grafo (Relaciones)</div>

      <div
        ref={containerRef}
        style={{
          height,
          border: "1px solid rgba(148, 163, 184, 0.25)",
          borderRadius: 12,
          background: "rgba(2, 6, 23, 0.25)",
        }}
      >
        {!hasData ? (
          <div style={{ padding: 18, color: "#94a3b8" }}>Sin datos para el grafo.</div>
        ) : null}
      </div>
    </div>
  );
}