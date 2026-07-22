// frontend/src/components/GraphView.tsx
import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";

cytoscape.use(fcose);

interface GraphData {
  nodes: { id: string; label: string; weight?: number; group?: string }[];
  edges: { id?: string; source: string; target: string; weight?: number }[];
}

interface Props {
  data: GraphData;
}

const NODE_COLORS = [
  "#E74C3C", "#E67E22", "#F1C40F", "#2ECC71",
  "#1ABC9C", "#3498DB", "#9B59B6", "#E91E63",
  "#00BCD4", "#FF5722", "#8BC34A", "#673AB7",
];

const EDGE_COLORS = [
  "#E74C3C88", "#E67E2288", "#3498DB88", "#9B59B688",
  "#2ECC7188", "#F1C40F88", "#E91E6388", "#00BCD488",
];

export default function GraphView({ data }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  useEffect(() => {
    // ✅ Validación de datos
    if (!containerRef.current || !data?.nodes?.length) return;

    // ✅ Destruir instancia previa
    if (cyRef.current) {
      cyRef.current.destroy();
      cyRef.current = null;
    }

    // ✅ Asignar colores por índice
    const groupMap: Record<string, number> = {};
    data.nodes.forEach((n, i) => {
      groupMap[n.id] = i % NODE_COLORS.length;
    });

    // ✅ Escala de tamaño por peso
    const weights = data.nodes.map((n) => n.weight || 1);
    const maxW = Math.max(...weights);
    const minW = Math.min(...weights);
    const nodeSize = (w: number) =>
      minW === maxW ? 45 : 28 + ((w - minW) / (maxW - minW)) * 50;

    // ✅ Escala de grosor de aristas
    const edgeWeights = data.edges.map((e) => e.weight || 1);
    const maxEW = Math.max(...edgeWeights);
    const edgeWidth = (w: number) => 1 + ((w || 1) / maxEW) * 6;

    // ✅ Inicializar Cytoscape
    cyRef.current = cytoscape({
      container: containerRef.current,

      elements: [
        ...data.nodes.map((n) => ({
          data: {
            id: n.id,
            label: n.label || n.id,
            weight: n.weight || 1,
            colorIdx: groupMap[n.id],
          },
        })),
        ...data.edges.map((e, i) => ({
          data: {
            id: e.id || `edge_${i}`,
            source: e.source,
            target: e.target,
            weight: e.weight || 1,
            colorIdx: i % EDGE_COLORS.length,
          },
        })),
      ],

      style: [
        {
          selector: "node",
          style: {
            width: (ele: any) => nodeSize(ele.data("weight")),
            height: (ele: any) => nodeSize(ele.data("weight")),
            "background-color": (ele: any) =>
              NODE_COLORS[ele.data("colorIdx") % NODE_COLORS.length],
            "border-width": 2,
            "border-color": "#ffffff",
            "border-opacity": 0.8,
            label: "data(label)",
            "text-valign": "center",
            "text-halign": "center",
            color: "#ffffff",
            "font-size": (ele: any) =>
              Math.max(9, Math.min(16, nodeSize(ele.data("weight")) / 3.5)),
            "font-weight": "bold",
            "font-family": "'Segoe UI', Arial, sans-serif",
            "text-outline-width": 1.5,
            "text-outline-color": (ele: any) =>
              NODE_COLORS[ele.data("colorIdx") % NODE_COLORS.length],
            "text-wrap": "wrap",
            "text-max-width": (ele: any) =>
              `${nodeSize(ele.data("weight")) * 0.9}px`,
            "overlay-padding": "6px",
            "z-index": 10,
          },
        },
        {
          selector: "node:hover",
          style: {
            "border-width": 4,
            "border-color": "#FFD700",
            "z-index": 999,
          },
        },
        {
          selector: "node.highlighted",
          style: {
            "border-width": 4,
            "border-color": "#FFD700",
            "z-index": 999,
          },
        },
        {
          selector: "edge",
          style: {
            width: (ele: any) => edgeWidth(ele.data("weight")),
            "line-color": (ele: any) =>
              EDGE_COLORS[ele.data("colorIdx") % EDGE_COLORS.length],
            "target-arrow-color": (ele: any) =>
              EDGE_COLORS[ele.data("colorIdx") % EDGE_COLORS.length],
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            opacity: 0.7,
          },
        },
        {
          selector: "edge:hover",
          style: {
            opacity: 1,
            width: (ele: any) => edgeWidth(ele.data("weight")) + 2,
          },
        },
        {
          selector: "edge.highlighted",
          style: {
            opacity: 1,
            "line-color": "#FFD700",
            "target-arrow-color": "#FFD700",
          },
        },
      ],

      layout: {
        name: "fcose",
        animate: true,
        animationDuration: 1200,
        animationEasing: "ease-out-cubic",
        fit: true,
        padding: 40,
        randomize: false,
        // Parámetros de física fcose
        nodeRepulsion: 6500,
        idealEdgeLength: 120,
        edgeElasticity: 0.45,
        nestingFactor: 0.1,
        gravity: 0.35,
        numIter: 2500,
        tile: true,
        tilingPaddingVertical: 20,
        tilingPaddingHorizontal: 20,
        gravityRangeCompound: 1.5,
        gravityCompound: 1.0,
        gravityRange: 3.8,
      } as any,

      // ✅ Opciones de interacción
      userZoomingEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
    });

    const cy = cyRef.current;

    // ✅ Hover: resaltar nodo y sus vecinos
    cy.on("mouseover", "node", (evt) => {
      const node = evt.target;
      node.addClass("highlighted");
      node.neighborhood().addClass("highlighted");
    });

    cy.on("mouseout", "node", (evt) => {
      const node = evt.target;
      node.removeClass("highlighted");
      node.neighborhood().removeClass("highlighted");
    });

    // ✅ Click: hacer fit al nodo
    cy.on("tap", "node", (evt) => {
      const node = evt.target;
      cy.animate({
        fit: { eles: node.closedNeighborhood(), padding: 60 },
        duration: 400,
        easing: "ease-in-out-cubic",
      });
    });

    // ✅ Doble click en fondo: reset zoom
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        cy.animate({
          fit: { eles: cy.elements(), padding: 40 },
          duration: 400,
          easing: "ease-in-out-cubic",
        });
      }
    });

    // ✅ Cleanup
    return () => {
      if (cyRef.current) {
        cyRef.current.destroy();
        cyRef.current = null;
      }
    };
  }, [data]);

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "500px",
        background: "linear-gradient(135deg, #0f1923 0%, #1a2a3a 100%)",
        borderRadius: "12px",
        overflow: "hidden",
        border: "1px solid rgba(255,255,255,0.1)",
      }}
    >
      {/* Título del grafo */}
      <div
        style={{
          position: "absolute",
          top: 12,
          left: 16,
          zIndex: 10,
          color: "rgba(255,255,255,0.6)",
          fontSize: "12px",
          fontFamily: "'Segoe UI', sans-serif",
          letterSpacing: "0.5px",
        }}
      >
        🔗 Grafo de relaciones — scroll para zoom · click para enfocar
      </div>

      {/* Contenedor Cytoscape */}
      <div
        ref={containerRef}
        style={{ width: "100%", height: "100%" }}
      />
    </div>
  );
}