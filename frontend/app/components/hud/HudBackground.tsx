"use client";

/**
 * HudBackground — Rejilla de fondo con efecto de perspectiva.
 * Dos planos en CSS 3D (suelo y techo) con líneas cada 50px, azul muy
 * oscuro a opacidad 0.1, rotados en perspectiva para que las celdas se
 * vean grandes en el centro y pequeñas hacia los bordes.
 */
export default function HudBackground() {
  const gridStyle: React.CSSProperties = {
    backgroundImage:
      "linear-gradient(rgba(0, 68, 170, 0.1) 1px, transparent 1px)," +
      "linear-gradient(90deg, rgba(0, 68, 170, 0.1) 1px, transparent 1px)",
    backgroundSize: "50px 50px",
  };

  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-0 overflow-hidden bg-[#050505]"
      style={{ perspective: "900px" }}
    >
      {/* Suelo en perspectiva */}
      <div
        className="absolute left-[-50%] top-[62%] h-[150%] w-[200%]"
        style={{
          ...gridStyle,
          transform: "rotateX(60deg)",
          transformOrigin: "top center",
          maskImage:
            "radial-gradient(ellipse at 50% 0%, black 20%, transparent 70%)",
          WebkitMaskImage:
            "radial-gradient(ellipse at 50% 0%, black 20%, transparent 70%)",
        }}
      />
      {/* Techo en perspectiva (espejo) */}
      <div
        className="absolute left-[-50%] bottom-[62%] h-[150%] w-[200%]"
        style={{
          ...gridStyle,
          transform: "rotateX(-60deg)",
          transformOrigin: "bottom center",
          maskImage:
            "radial-gradient(ellipse at 50% 100%, black 20%, transparent 70%)",
          WebkitMaskImage:
            "radial-gradient(ellipse at 50% 100%, black 20%, transparent 70%)",
        }}
      />
      {/* Viñeta central para dar profundidad */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse at center, transparent 40%, rgba(2,6,13,0.85) 100%)",
        }}
      />
    </div>
  );
}
