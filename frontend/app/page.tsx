"use client";

/**
 * Página principal de J.A.R.V.I.S.
 *
 * - Renderiza el JarvisHUD a pantalla completa (sin scroll)
 * - Estado local `jarvisStatus` que comienza en 'idle'
 * - El estado se pasa al HUD, que lo reenvía a JarvisCore
 * - 4 botones de prueba en la parte inferior central para
 *   cambiar manualmente el estado del núcleo
 */
import { useState } from "react";
import JarvisHUD from "@/app/components/JarvisHUD";
import type { JarvisStatus } from "@/app/components/JarvisCore";

const STATUS_BUTTONS: { label: string; value: JarvisStatus }[] = [
  { label: "IDLE", value: "idle" },
  { label: "LISTEN", value: "listening" },
  { label: "THINK", value: "thinking" },
  { label: "SPEAK", value: "speaking" },
];

export default function Home() {
  const [jarvisStatus, setJarvisStatus] = useState<JarvisStatus>("idle");

  return (
    <main className="fixed inset-0 h-screen w-screen overflow-hidden bg-[#050505]">
      {/* HUD completo con el núcleo centrado (recibe el estado actual) */}
      <JarvisHUD status={jarvisStatus} />

      {/* Botones de prueba de estados — parte inferior central */}
      <div className="pointer-events-auto fixed bottom-6 left-1/2 z-[100] flex -translate-x-1/2 gap-3">
        {STATUS_BUTTONS.map(({ label, value }) => {
          const active = jarvisStatus === value;
          return (
            <button
              key={value}
              type="button"
              onClick={() => setJarvisStatus(value)}
              className="rounded border border-[#00f3ff] bg-transparent px-3 py-1 font-mono text-xs uppercase tracking-widest text-[#00f3ff] transition-colors duration-200 hover:bg-[#00f3ff] hover:text-black focus:outline-none focus:ring-1 focus:ring-[#00f3ff]/60"
              style={{
                boxShadow: active
                  ? "0 0 10px rgba(0,243,255,0.8), inset 0 0 6px rgba(0,243,255,0.4)"
                  : "0 0 4px rgba(0,243,255,0.35)",
                ...(active
                  ? { backgroundColor: "#00f3ff", color: "#000" }
                  : null),
              }}
            >
              {label}
            </button>
          );
        })}
      </div>
    </main>
  );
}
