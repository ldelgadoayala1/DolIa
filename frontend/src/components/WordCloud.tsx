import React, { useEffect, useMemo, useRef, useState } from "react";
import cloud from "d3-cloud";

export type WordItem = { word: string; weight: number };

type Props = {
  wordcloud?: WordItem[];
  width?: number;
  height?: number;
};

export default function WordCloud({
  wordcloud = [],
  width = 700,
  height = 320,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [renderSeed, setRenderSeed] = useState(0);

  const sorted = useMemo(() => {
    if (!wordcloud) return [];
    return [...wordcloud]
      .filter((w) => w?.word && typeof w.weight === "number")
      .sort((a, b) => b.weight - a.weight);
  }, [wordcloud]);

  const hasData = sorted.length > 0;

  useEffect(() => {
    setRenderSeed((s) => s + 1);
  }, [sorted]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, width, height);

    if (!hasData) return;

    const maxWords = 60; // legibilidad
    const words = sorted.slice(0, maxWords);

    const maxW = Math.max(...words.map((d) => d.weight), 1);
    const minFont = 12;
    const maxFont = 46;

    const fontScale = (w: number) => {
      const t = w / maxW;
      return minFont + t * (maxFont - minFont);
    };

    const layout = cloud()
      .canvas(canvas as any)
      .size([width, height])
      .words(words.map((d) => ({ text: d.word, size: fontScale(d.weight) })))
      .padding(4)
      .rotate(() => (Math.random() > 0.82 ? 90 : 0))
      .font("sans-serif")
      .fontSize((d: any) => d.size)
      .on("end", (items: any[]) => {
        ctx.clearRect(0, 0, width, height);

        const cx = width / 2;
        const cy = height / 2;

        items.forEach((d) => {
          ctx.save();
          ctx.translate(cx + d.x, cy + d.y);
          ctx.rotate((d.rotate * Math.PI) / 180);

          const alpha = Math.min(1, Math.max(0.35, d.size / maxFont));
          ctx.fillStyle = `rgba(52, 211, 153, ${alpha})`;

          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.font = `600 ${d.size}px sans-serif`;

          ctx.fillText(d.text, 0, 0);
          ctx.restore();
        });
      });

    // // variación controlada
    // layout.randomSource(() => {
    //   let x = (renderSeed * 99991 + 12345) >>> 0;
    //   x = (x ^ (x << 13)) >>> 0;
    //   return (x % 1000) / 1000;
    // });

    layout.start();

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sorted, width, height, hasData, renderSeed]);

  return (
    <div style={{ width: "100%" }}>
      <div style={{ fontWeight: 700, marginBottom: 8 }}>Nube de palabras (IA)</div>

      <div
        style={{
          border: "1px solid rgba(148, 163, 184, 0.25)",
          borderRadius: 12,
          padding: 10,
          background: "rgba(2, 6, 23, 0.25)",
        }}
      >
        {!hasData ? (
          <div style={{ padding: "18px 8px", color: "#94a3b8" }}>
            Sin datos para la nube de palabras.
          </div>
        ) : (
          <canvas
            ref={canvasRef}
            width={width}
            height={height}
            style={{ width: "100%", height }}
          />
        )}
      </div>
    </div>
  );
}