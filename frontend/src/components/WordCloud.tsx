// frontend/src/components/WordCloud.tsx
import { useEffect, useRef } from "react";
import * as d3 from "d3";
import cloud from "d3-cloud";

interface Word {
  text: string;
  value: number;
}

interface Props {
  words: Word[];
}

// Paleta de azules + acento rojo UNAB (como la referencia)
const COLOR_PALETTE = [
  "#1B3A6B", // azul oscuro UNAB
  "#2E5FA3", // azul medio UNAB
  "#4A90D9", // azul claro
  "#6FB3E0", // azul cielo
  "#1A7FC1", // azul brillante
  "#0D5C8F", // azul profundo
  "#3B82C4", // azul intermedio
  "#C8102E", // rojo UNAB (acento)
  "#2196F3", // azul material
  "#1565C0", // azul intenso
];

export default function WordCloud({ words }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!words || words.length === 0 || !svgRef.current) return;

    const container = svgRef.current.parentElement;
    const width = container?.clientWidth || 700;
    const height = 420;

    // Limpiar SVG anterior
    d3.select(svgRef.current).selectAll("*").remove();

    // Escala de tamaño de fuente
    const maxVal = Math.max(...words.map((w) => w.value));
    const minVal = Math.min(...words.map((w) => w.value));

    const fontSizeScale = d3
      .scaleLinear()
      .domain([minVal, maxVal])
      .range([14, 80]);

    // Escala de color por frecuencia
    const colorScale = d3
      .scaleQuantize<string>()
      .domain([minVal, maxVal])
      .range(COLOR_PALETTE);

    // Generar layout de nube
    cloud()
      .size([width, height])
      .words(
        words.map((w) => ({
          text: w.text,
          size: fontSizeScale(w.value),
          value: w.value,
        }))
      )
      .padding(4)
      .rotate(() => {
        // Mayoría horizontal, algunos rotados como la referencia
        const angles = [0, 0, 0, 90, -90];
        return angles[Math.floor(Math.random() * angles.length)];
      })
      .font("'Segoe UI', 'Arial', sans-serif")
      .fontSize((d: any) => d.size)
      .on("end", draw)
      .start();

    function draw(computedWords: any[]) {
      const svg = d3.select(svgRef.current);

      svg
        .attr("width", width)
        .attr("height", height)
        .style("background", "transparent");

      const g = svg
        .append("g")
        .attr("transform", `translate(${width / 2},${height / 2})`);

      g.selectAll("text")
        .data(computedWords)
        .enter()
        .append("text")
        .style("font-family", "'Segoe UI', 'Arial', sans-serif")
        .style("font-weight", (d: any) => (d.size > 40 ? "800" : d.size > 25 ? "700" : "500"))
        .style("fill", (d: any) => colorScale(d.value))
        .style("cursor", "pointer")
        .style("opacity", 0)
        .attr("text-anchor", "middle")
        .attr("transform", (d: any) => `translate(${d.x},${d.y}) rotate(${d.rotate})`)
        .attr("font-size", (d: any) => `${d.size}px`)
        .text((d: any) => d.text)
        // Animación de entrada
        .transition()
        .duration(600)
        .delay((_, i) => i * 20)
        .style("opacity", 1)
        // Hover interactivo
        .selection()
        .on("mouseover", function (event: any, d: any) {
          d3.select(this)
            .transition()
            .duration(200)
            .style("opacity", 0.75)
            .attr("font-size", `${d.size * 1.15}px`);

          // Tooltip
          tooltip
            .style("display", "block")
            .html(`<strong>${d.text}</strong><br/>Frecuencia: ${d.value}`)
            .style("left", `${event.offsetX + 12}px`)
            .style("top", `${event.offsetY - 28}px`);
        })
        .on("mouseout", function (_, d: any) {
          d3.select(this)
            .transition()
            .duration(200)
            .style("opacity", 1)
            .attr("font-size", `${d.size}px`);

          tooltip.style("display", "none");
        });
    }

    // Tooltip DOM
    const parentEl = svgRef.current.parentElement!;
    let tooltip = d3.select(parentEl).select<HTMLDivElement>(".wc-tooltip");
    if (tooltip.empty()) {
      tooltip = d3
        .select(parentEl)
        .append("div")
        .attr("class", "wc-tooltip")
        .style("position", "absolute")
        .style("background", "rgba(27,58,107,0.92)")
        .style("color", "#fff")
        .style("padding", "6px 12px")
        .style("border-radius", "6px")
        .style("font-size", "13px")
        .style("pointer-events", "none")
        .style("display", "none")
        .style("z-index", "100")
        .style("box-shadow", "0 2px 8px rgba(0,0,0,0.3)");
    }
  }, [words]);

  return (
    <div style={{ position: "relative", width: "100%", minHeight: 420 }}>
      <svg ref={svgRef} style={{ width: "100%", height: 420 }} />
    </div>
  );
}