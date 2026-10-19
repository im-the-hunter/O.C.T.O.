"use client";

/**
 * JarvisHUD — Layout principal de la interfaz J.A.R.V.I.S.
 *
 * - Pantalla completa (100vw x 100vh) con fondo negro #050505
 * - Rejilla sutil de fondo (líneas cada 50px, azul muy oscuro op 0.1)
 * - JarvisCore centrado en el centro exacto de la pantalla
 * - 4 esquinas con información estilo HUD
 * - Fuente Orbitron (Google Fonts) + efecto glow (text-shadow)
 */
import { useEffect, useState, type FC } from "react";
import JarvisCore, { type JarvisStatus } from "./JarvisCore";

interface JarvisHUDProps {
  status?: JarvisStatus;
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

const randomInRange = (min: number, max: number) =>
  Math.floor(min + Math.random() * (max - min));

const formatTime = (d: Date) =>
  d.toLocaleTimeString("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });

/* ------------------------------------------------------------------ */
/* Sub-componente: línea de texto HUD con glow                         */
/* ------------------------------------------------------------------ */

const HudLine: FC<{ children: React.ReactNode; dim?: boolean }> = ({
  children,
  dim = false,
}) => (
  <p
    className="font-orbitron text-[11px] sm:text-xs tracking-widest uppercase"
    style={{
      color: "#00f3ff",
      opacity: dim ? 0.7 : 1,
      textShadow: "0 0 6px rgba(0, 243, 255, 0.65), 0 0 14px rgba(0, 243, 255, 0.35)",
    }}
  >
    {children}
  </p>
);

/* ------------------------------------------------------------------ */
/* Componente principal                                                */
/* ------------------------------------------------------------------ */

const JarvisHUD: FC<JarvisHUDProps> = ({ status = "idle" }) => {
  /* Hora actual — se actualiza cada segundo */
  const [time, setTime] = useState<string>(() => formatTime(new Date()));

  /* Métricas simuladas — refrescadas cada 2 segundos */
  const [cpu, setCpu] = useState<number>(() => randomInRange(20, 40));
  const [memory, setMemory] = useState<number>(() => randomInRange(40, 60));

  useEffect(() => {
    const clock = setInterval(() => setTime(formatTime(new Date())), 1000);
    const telemetry = setInterval(() => {
      setCpu(randomInRange(20, 40));
      setMemory(randomInRange(40, 60));
    }, 2000);
    return () => {
      clearInterval(clock);
      clearInterval(telemetry);
    };
  }, []);

  return (
    <div className="fixed inset-0 h-screen w-screen overflow-hidden bg-[#050505]">
      {/* Fuente Orbitron desde Google Fonts */}
      <link
        href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;700;900&display=swap"
        rel="stylesheet"
      />

      {/* Rejilla de fondo: líneas cada 50px, azul muy oscuro con opacidad 0.1 */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage:
            "linear-gradient(rgba(0, 68, 170, 0.1) 1px, transparent 1px)," +
            "linear-gradient(90deg, rgba(0, 68, 170, 0.1) 1px, transparent 1px)",
          backgroundSize: "50px 50px",
        }}
      />

      {/* Núcleo en el centro exacto de la pantalla */}
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
        <JarvisCore status={status} />
      </div>

      {/* Esquina superior izquierda — identidad del sistema */}
      <div className="absolute left-4 top-4 space-y-1 sm:left-6 sm:top-6">
        <p
          className="font-orbitron text-lg font-bold tracking-[0.25em] sm:text-2xl"
          style={{
            color: "#00f3ff",
            textShadow:
              "0 0 10px rgba(0, 243, 255, 0.8), 0 0 24px rgba(0, 243, 255, 0.4)",
          }}
        >
          J.A.R.V.I.S. v2.0
        </p>
        <HudLine>System Status: Online</HudLine>
        <HudLine>{time}</HudLine>
      </div>

      {/* Esquina superior derecha — estado del repositorio */}
      <div className="absolute right-4 top-4 space-y-1 text-right sm:right-6 sm:top-6">
        <HudLine>Repo: O.C.T.O.</HudLine>
        <HudLine>Branch: feature/jarvis-initial-setup</HudLine>
        <HudLine>Status: Synced</HudLine>
      </div>

      {/* Esquina inferior izquierda — telemetría del sistema */}
      <div className="absolute bottom-4 left-4 space-y-1 sm:bottom-6 sm:left-6">
        <HudLine>CPU: {cpu}%</HudLine>
        <HudLine>Memory: {memory}%</HudLine>
        <HudLine>Network: Active</HudLine>
      </div>

      {/* Esquina inferior derecha — subsistemas de IA */}
      <div className="absolute bottom-4 right-4 space-y-1 text-right sm:bottom-6 sm:right-6">
        <HudLine>Voice: Ready</HudLine>
        <HudLine>Model: GPT-4o</HudLine>
        <HudLine>RAG: Active</HudLine>
      </div>
    </div>
  );
};

export default JarvisHUD;
