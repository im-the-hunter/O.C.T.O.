"use client";

/**
 * SoundManager (Fase 3) — Sistema de sonido completo basado en Howler.js.
 *
 * - Carga todos los SFX al iniciar la app (preload).
 * - Zumbido ambiental en loop cuyo volumen se ajusta según la actividad
 *   del sistema (idle → 0.2, thinking/listening → 0.28, speaking → 0.15).
 * - Mute/unmute global persistido en localStorage.
 * - Soporte opcional de ElevenLabs: si hay clave configurada y el texto
 *   supera el umbral, speechSynthesis delega en un audio generado.
 *
 * Expuesto como contexto para que cualquier componente del HUD pueda
 * disparar sonidos: const sfx = useSound();
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Howl, Howler } from "howler";
import { soundManager, type SoundName } from "./soundManager";
import type { JarvisState } from "@/lib/jarvis-state";

/* ------------------------------------------------------------------ */
/* Niveles de volumen del ambient-hum según estado                     */
/* ------------------------------------------------------------------ */

const HUM_VOLUME: Record<JarvisState, number> = {
  idle: 0.2,
  listening: 0.26, // sube ligeramente cuando el micro captura audio
  thinking: 0.3, // "los reactores trabajan"
  speaking: 0.14, // baja para no tapar la voz de JARVIS
};

/* ------------------------------------------------------------------ */
/* Contexto                                                            */
/* ------------------------------------------------------------------ */

interface SoundContextValue {
  muted: boolean;
  toggleMute: () => void;
  setMuted: (m: boolean) => void;
  masterVolume: number;
  setMasterVolume: (v: number) => void;
  play: (name: SoundName, volume?: number) => void;
  /** true si el motor TTS es ElevenLabs (calidad premium) */
  elevenLabsEnabled: boolean;
}

const SoundContext = createContext<SoundContextValue | null>(null);

export function useSound(): SoundContextValue {
  const ctx = useContext(SoundContext);
  if (!ctx) throw new Error("useSound debe usarse dentro de <SoundProvider>");
  return ctx;
}

/* ------------------------------------------------------------------ */
/* Provider                                                            */
/* ------------------------------------------------------------------ */

export function SoundProvider({
  children,
  state,
}: {
  children: ReactNode;
  state: JarvisState;
}) {
  const [muted, setMutedState] = useState(false);
  const [masterVolume, setMasterVolumeState] = useState(0.8);
  const humRef = useRef<Howl | null>(null);
  const startedRef = useRef(false);

  const elevenLabsEnabled = useMemo(() => {
    if (typeof window === "undefined") return false;
    return Boolean(process.env.NEXT_PUBLIC_ELEVENLABS_API_KEY);
  }, []);

  /* --- Restaurar preferencia de mute ------------------------------- */
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem("jarvis-muted");
      if (stored !== null) setMutedState(stored === "1");
    } catch {
      /* almacenamiento bloqueado: ignorar */
    }
  }, []);

  /* --- Cargar e iniciar el ambient-hum tras el primer gesto -------- */
  useEffect(() => {
    if (startedRef.current) return;
    const unlock = () => {
      if (startedRef.current) return;
      startedRef.current = true;
      // El ambient-hum sólo suena tras una interacción (política autoplay).
      const hum = new Howl({
        src: ["/sounds/ambient-hum.mp3"],
        loop: true,
        volume: 0,
        html5: false,
      });
      hum.play();
      // Fade-in suave hasta el nivel del estado actual
      hum.fade(0, HUM_VOLUME[state], 1500);
      humRef.current = hum;
      soundManager.setMasterVolume(muted ? 0 : masterVolume);
    };
    window.addEventListener("pointerdown", unlock, { once: true });
    window.addEventListener("keydown", unlock, { once: true });
    return () => {
      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("keydown", unlock);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* --- Ajustar volumen del hum según actividad ---------------------- */
  useEffect(() => {
    const hum = humRef.current;
    if (!hum || !startedRef.current) return;
    const target = muted ? 0 : HUM_VOLUME[state];
    hum.fade(hum.volume(), target, 600);
  }, [state, muted]);

  /* --- Aplicar volumen maestro / mute ------------------------------ */
  useEffect(() => {
    soundManager.setMasterVolume(muted ? 0 : masterVolume);
    try {
      window.localStorage.setItem("jarvis-muted", muted ? "1" : "0");
    } catch {
      /* ignorar */
    }
  }, [muted, masterVolume]);

  /* --- Suspender/reanudar Howler al ocultar la pestaña -------------- */
  useEffect(() => {
    const onVis = () => {
      if (document.hidden) Howler.mute(true);
      else if (!muted) Howler.unmute();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, [muted]);

  const setMuted = useCallback((m: boolean) => setMutedState(m), []);
  const toggleMute = useCallback(
    () => setMutedState((m) => !m),
    []
  );
  const setMasterVolume = useCallback(
    (v: number) => setMasterVolumeState(Math.min(1, Math.max(0, v))),
    []
  );
  const play = useCallback((name: SoundName, volume?: number) => {
    soundManager.play(name, volume);
  }, []);

  const value = useMemo(
    () => ({
      muted,
      toggleMute,
      setMuted,
      masterVolume,
      setMasterVolume,
      play,
      elevenLabsEnabled,
    }),
    [muted, toggleMute, setMuted, masterVolume, setMasterVolume, play, elevenLabsEnabled]
  );

  return <SoundContext.Provider value={value}>{children}</SoundContext.Provider>;
}
