"use client";

/**
 * JarvisHUD — Layout de pantalla completa (100vw × 100vh).
 * Cuatro clusters de telemetría en las esquinas + núcleo central.
 * El panel de chat se renderiza aparte (page.tsx) para poder ser
 * lateral en desktop e inferior en móvil.
 */
import { useEffect, useState } from "react";
import StatusIndicator from "@/components/ui/StatusIndicator";
import { useJarvis } from "@/lib/jarvis-state";

/* ------------------------------------------------------------------ */
/* Hook: reloj 24h + fecha                                              */
/* ------------------------------------------------------------------ */

function useClock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

/* ------------------------------------------------------------------ */
/* Utilidad: métricas simuladas que fluctúan suavemente                 */
/* ------------------------------------------------------------------ */

function useSimulatedLoad(value: number, variance: number) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setInterval(() => {
      setV((prev) => {
        const next = prev + (Math.random() * 2 - 1) * variance;
        return Math.max(3, Math.min(97, Math.round(next)));
      });
    }, 2000);
    return () => clearInterval(id);
  }, [variance]);
  // value tiene prioridad si cambia desde el contexto
  useEffect(() => setV(value), [value]);
  return v;
}

/* ------------------------------------------------------------------ */
/* Línea de telemetría                                                 */
/* ------------------------------------------------------------------ */

function TelemetryRow({
  label,
  value,
  accent,
}: {
  label: string;
  value: React.ReactNode;
  accent?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4 font-tech text-[10px] uppercase tracking-widest md:text-xs">
      <span className="text-jarvis/50">{label}</span>
      <span style={{ color: accent ?? "#7df9ff" }} className="text-glow-cyan-soft">
        {value}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Componente principal                                                 */
/* ------------------------------------------------------------------ */

export default function JarvisHUD() {
  const { state, metrics } = useJarvis();
  const now = useClock();
  const cpu = useSimulatedLoad(metrics.cpu, 6);
  const mem = useSimulatedLoad(metrics.memory, 4);

  const time = now
    ? now.toLocaleTimeString("es-ES", { hour12: false })
    : "--:--:--";
  const date = now
    ? now.toLocaleDateString("es-ES", {
        weekday: "short",
        day: "2-digit",
        month: "short",
        year: "numeric",
      })
    : "";

  return (
    <div className="pointer-events-none fixed inset-0 z-30 select-none">
      {/* ================= Esquina superior izquierda ================= */}
      <div className="absolute left-4 top-4 space-y-1 md:left-6 md:top-6">
        <p className="font-display text-sm font-bold tracking-[0.35em] text-jarvis text-glow md:text-lg">
          J.A.R.V.I.S. <span className="text-holo-light">v2.0</span>
        </p>
        <div className="flex items-center gap-2">
          <StatusIndicator color="#00ff9d" />
          <TelemetryRow label="System Status:" value="ONLINE" accent="#00ff9d" />
        </div>
        <TelemetryRow label="Time:" value={time} />
        <TelemetryRow label="Date:" value={date.toUpperCase()} />
      </div>

      {/* ================= Esquina superior derecha ================= */}
      <div className="absolute right-4 top-4 space-y-1 text-right md:right-6 md:top-6">
        <TelemetryRow label="Repo Synced:" value={`[ ${metrics.repoName} ]`} />
        <TelemetryRow label="Last Commit:" value={metrics.lastCommit} />
        <TelemetryRow label="Branch:" value={metrics.branch} />
        <div className="flex items-center justify-end gap-2">
          <TelemetryRow
            label="GitHub Actions:"
            value={metrics.ciGreen ? "PASSING" : "FAILING"}
            accent={metrics.ciGreen ? "#00ff9d" : "#ff3b5c"}
          />
          <StatusIndicator color={metrics.ciGreen ? "#00ff9d" : "#ff3b5c"} pulse={false} />
        </div>
      </div>

      {/* ================= Esquina inferior izquierda ================= */}
      <div className="absolute bottom-4 left-4 space-y-1 md:bottom-6 md:left-6">
        <TelemetryRow label="CPU:" value={`${cpu}%`} accent={cpu > 80 ? "#ffb347" : undefined} />
        <TelemetryRow label="Memory:" value={`${mem}%`} accent={mem > 85 ? "#ffb347" : undefined} />
        <TelemetryRow label="Network:" value="ACTIVE" accent="#00ff9d" />
        <TelemetryRow
          label="Vector DB:"
          value={metrics.vectorDbConnected ? "CONNECTED" : "OFFLINE"}
          accent={metrics.vectorDbConnected ? "#00ff9d" : "#ff3b5c"}
        />
      </div>

      {/* ================= Esquina inferior derecha ================= */}
      <div className="absolute bottom-4 right-4 space-y-1 text-right md:bottom-6 md:right-6">
        <TelemetryRow
          label="Voice:"
          value={state === "listening" ? "LISTENING" : "READY"}
          accent={state === "listening" ? "#ff6b00" : "#00ff9d"}
        />
        <TelemetryRow label="Model:" value="GPT-4o" />
        <TelemetryRow
          label="Context:"
          value={`${metrics.contextTokens.toLocaleString()} tokens`}
        />
      </div>

      {/* Marcas decorativas de esquina (brackets) */}
      {["left-2 top-2 border-l border-t", "right-2 top-2 border-r border-t",
        "left-2 bottom-2 border-b border-l", "right-2 bottom-2 border-b border-r"].map(
        (pos) => (
          <div
            key={pos}
            aria-hidden
            className={`absolute h-6 w-6 border-jarvis/40 ${pos}`}
          />
        )
      )}
    </div>
  );
}
