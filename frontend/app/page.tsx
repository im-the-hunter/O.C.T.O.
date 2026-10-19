/**
 * Página principal del HUD de J.A.R.V.I.S. (Fase 2)
 * Composición: fondo con grid en perspectiva → partículas → núcleo →
 * telemetría HUD → scanline → panel de chat (lateral en desktop,
 * inferior en móvil).
 */
import dynamic from "next/dynamic";
import { JarvisProvider, useJarvis } from "@/lib/jarvis-state";
import { SoundProvider } from "@/lib/sound/SoundManager";
import JarvisHUD from "@/components/hud/JarvisHUD";
import HudBackground from "@/components/hud/HudBackground";
import ScanLine from "@/components/hud/ScanLine";
import VoiceController from "@/components/hud/VoiceController";

// El núcleo y las partículas usan canvas/GSAP: sólo cliente, sin SSR.
const JarvisCore = dynamic(() => import("@/components/core/JarvisCore"), {
  ssr: false,
});
const ParticleField = dynamic(() => import("@/components/core/ParticleField"), {
  ssr: false,
});
const ChatPanel = dynamic(() => import("@/components/chat/ChatPanel"), {
  ssr: false,
});

export default function Home() {
  return (
    <JarvisProvider>
      <SoundGate>
        <main className="relative h-screen w-screen overflow-hidden bg-[#050505]">
          {/* Capa 0: rejilla con perspectiva */}
          <HudBackground />

          {/* Capa 0.5: partículas orbitando el núcleo */}
          <ParticleField />

          {/* Capa 1: núcleo SVG centrado (desplazado a la izquierda en desktop
              para compensar el panel de chat lateral de 400px) */}
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center lg:pr-[400px]">
            <JarvisCore />
          </div>

          {/* Capa 2: telemetría en las 4 esquinas */}
          <JarvisHUD />

          {/* Capa 3: scanline global */}
          <ScanLine />

          {/* Capa 4: panel de chat — lateral derecho (desktop) / inferior (móvil) */}
          <aside className="pointer-events-auto fixed bottom-0 right-0 z-50 h-[300px] w-full p-3 md:p-4 lg:bottom-0 lg:right-0 lg:h-full lg:w-[400px] lg:p-6">
            <ChatPanel />
          </aside>

          {/* Capa 5 (Fase 3): orquestador de voz + barra de control */}
          <VoiceController />
        </main>
      </SoundGate>
    </JarvisProvider>
  );
}

/**
 * Envuelve el HUD en SoundProvider passing the current JarvisState so
 * the ambient-hum volume tracks system activity. Needs its own component
 * to consume the context.
 */
function SoundGate({ children }: { children: React.ReactNode }) {
  const { state } = useJarvis();
  return <SoundProvider state={state}>{children}</SoundProvider>;
}
