/**
 * Página principal del HUD de J.A.R.V.I.S.
 * Fase 1: estructura base. Los componentes del HUD, núcleo SVG y chat
 * se implementarán en las próximas fases.
 */
export default function Home() {
  return (
    <main className="hud-background relative flex min-h-screen flex-col items-center justify-center overflow-hidden p-hud">
      {/* Capa de rejilla holográfica */}
      <div className="pointer-events-none absolute inset-0 bg-hud-grid bg-grid opacity-40" />

      {/* Contenedor del HUD (Fase 2: <JarvisCore />, <ChatPanel />, <HUDOverlay />) */}
      <section className="hud-panel z-10 flex flex-col items-center gap-6 px-12 py-10">
        <h1 className="hud-text text-glow text-3xl font-bold tracking-[0.4em] md:text-5xl">
          J.A.R.V.I.S.
        </h1>
        <p className="max-w-md text-center text-xs uppercase tracking-widest text-abyss-light md:text-sm">
          Sistema de inteligencia artificial listo. Esperando instrucciones, señor.
        </p>
        <div className="flex gap-4">
          <button className="hud-button animate-flicker">Iniciar Sesión</button>
          <button className="hud-button">Activar Voz</button>
        </div>
      </section>

      {/* Línea de escaneo decorativa */}
      <div className="pointer-events-none absolute left-0 top-0 h-px w-full bg-jarvis/30 shadow-glow-cyan animate-scanline" />
    </main>
  );
}
