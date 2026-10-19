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
import { useEffect, useState } from "react";
import JarvisHUD from "@/app/components/JarvisHUD";
import type { JarvisStatus } from "@/app/components/JarvisCore";
import { JarvisProvider, useJarvis, type JarvisState } from "@/lib/jarvis-state";
import { SoundProvider } from "@/lib/sound/SoundManager";
import HudBackground from "@/components/hud/HudBackground";
import ParticleField from "@/components/core/ParticleField";
import ScanLine from "@/components/hud/ScanLine";
import ChatPanel from "@/components/chat/ChatPanel";
import VoiceController from "@/components/hud/VoiceController";

const STATUS_BUTTONS: { label: string; value: JarvisStatus }[] = [
  { label: "IDLE", value: "idle" },
  { label: "LISTEN", value: "listening" },
  { label: "THINK", value: "thinking" },
  { label: "SPEAK", value: "speaking" },
];

const STATUS_TO_STATE: Record<string, JarvisState> = {
  idle: "idle",
  listening: "listening",
  thinking: "thinking",
  speaking: "speaking",
};

/** Puente: sincroniza el estado local de prueba con el estado global. */
function StatusBridge({ status }: { status: JarvisStatus }) {
  const { setState } = useJarvis();
  useEffect(() => {
    setState(STATUS_TO_STATE[status] ?? "idle");
  }, [status, setState]);
  return null;
}

function Interface({
  jarvisStatus,
  setJarvisStatus,
}: {
  jarvisStatus: JarvisStatus;
  setJarvisStatus: (s: JarvisStatus) => void;
}) {
  return (
    <main className="fixed inset-0 h-screen w-screen overflow-hidden bg-[#050505]">
      {/* Capas ambientales: rejilla en perspectiva, partículas y scanline */}
      <HudBackground />
      <ParticleField />
      <ScanLine />

      {/* HUD completo (esquinas + núcleo central) */}
      <JarvisHUD status={jarvisStatus} />

      {/* Panel de chat — lateral derecho en desktop, inferior en móvil */}
      <div className="pointer-events-auto fixed right-0 bottom-16 left-0 z-40 h-[38vh] md:top-0 md:left-auto md:h-full md:w-[400px] md:bottom-0">
        <ChatPanel />
      </div>

      {/* Orquestador de voz (Fase 3): wake word, TTS, comandos especiales */}
      <VoiceController />

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

/** Nivel interno: ya dentro de JarvisProvider, conecta el estado global al sonido. */
function InterfaceRoot({
  jarvisStatus,
  setJarvisStatus,
}: {
  jarvisStatus: JarvisStatus;
  setJarvisStatus: (s: JarvisStatus) => void;
}) {
  const { state } = useJarvis();
  return (
    <SoundProvider state={state}>
      <StatusBridge status={jarvisStatus} />
      <Interface
        jarvisStatus={jarvisStatus}
        setJarvisStatus={setJarvisStatus}
      />
    </SoundProvider>
  );
}

export default function Home() {
  const [jarvisStatus, setJarvisStatus] = useState<JarvisStatus>("idle");

  return (
    <JarvisProvider>
      <InterfaceRoot
        jarvisStatus={jarvisStatus}
        setJarvisStatus={setJarvisStatus}
      />
    </JarvisProvider>
  );
}
