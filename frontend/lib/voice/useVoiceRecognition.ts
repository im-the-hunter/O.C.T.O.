"use client";

/**
 * useVoiceRecognition (Fase 3) — Reconocimiento de voz con wake word.
 *
 * Basado en la Web Speech API (SpeechRecognition). Dos modos:
 *
 *  1. WAKE WORD: escucha continua en segundo plano buscando "JARVIS"
 *     (tolerante a fonética inglesa/española: jarvis, chárvis, harvis…).
 *     Al detectarlo dispara onWake() y pasa a modo comando.
 *
 *  2. COMANDO: captura el utterance completo con interimResults para
 *     mostrar el texto en tiempo real. Finaliza por:
 *       - resultado final (onend), o
 *       - 5 s de silencio sin cambios (timeout de inactividad), o
 *       - límite duro de 8 s.
 *
 * Incluye debounce anti-doble-activación y manejo de errores
 * (no-permission / no-speech / red / navegador no soportado).
 */
import { useCallback, useEffect, useRef, useState } from "react";

/* Tipos mínimos de la Web Speech API (no incluida en lib.dom) */
interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}
interface SpeechRecognitionResult {
  readonly length: number;
  isFinal: boolean;
  [index: number]: SpeechRecognitionAlternative;
}
interface SpeechRecognitionEventLike extends Event {
  resultIndex: number;
  results: { length: number; [index: number]: SpeechRecognitionResult };
}
interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onerror: ((e: Event & { error?: string }) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

export type VoiceLang = "es-ES" | "en-US";

export type VoiceError =
  | "unsupported" // navegador sin Web Speech API
  | "permission-denied" // micrófono denegado
  | "no-mic" // sin dispositivo de entrada
  | "no-speech" // silencio: no se detectó habla
  | "network" // fallo de red del servicio de reconocimiento
  | "aborted"; // cancelado programáticamente (ignorable)

export interface UseVoiceRecognitionOptions {
  /** Palabra de activación (normalizada en minúsculas) */
  wakeWord?: string;
  lang?: VoiceLang;
  /** ms sin cambios de transcript → se considera fin del comando */
  silenceTimeoutMs?: number;
  /** ms máximos de escucha de un comando */
  commandMaxMs?: number;
  /** ms de cooldown tras una activación (debounce anti-repetición) */
  wakeDebounceMs?: number;
  onWake?: () => void;
  /** Transcript parcial mientras se habla (tiempo real) */
  onInterim?: (text: string) => void;
  /** Transcript final del comando (sin la wake word) */
  onCommand?: (transcript: string) => void;
  onError?: (err: VoiceError) => void;
  onStart?: () => void;
  onEnd?: () => void;
}

const DEFAULT_WAKE = "jarvis";

/** Fonéticas aceptadas para el wake word (inglés + español aproximado) */
const WAKE_VARIANTS = ["jarvis", "jervis", "harvis", "charvis", "chárvis", "jálvis", "jarvi", "j.a.r.v.i.s"];

function normalize(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "") // tildes
    .replace(/[^a-z0-9\s.]/g, "")
    .trim();
}

function containsWake(text: string, wake: string): boolean {
  const n = normalize(text).replace(/\./g, "");
  const w = normalize(wake);
  if (n.includes(w)) return true;
  return WAKE_VARIANTS.some((v) => n.includes(v));
}

/** Devuelve el texto sin la ocurrencia del wake word */
function stripWake(text: string, wake: string): string {
  const tokens = text.split(/\s+/);
  const w = normalize(wake);
  for (let i = 0; i < tokens.length; i++) {
    const t = normalize(tokens[i]).replace(/\./g, "");
    if (t === w || WAKE_VARIANTS.includes(t)) {
      return tokens.slice(i + 1).join(" ").trim();
    }
  }
  return text.trim();
}

export function getCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  return (
    (window as unknown as { SpeechRecognition?: SpeechRecognitionCtor })
      .SpeechRecognition ??
    (window as unknown as { webkitSpeechRecognition?: SpeechRecognitionCtor })
      .webkitSpeechRecognition ??
    null
  );
}

/** Pide explícitamente permiso de micrófono (mejor UX que el implícito). */
export async function requestMicPermission(): Promise<boolean> {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((tr) => tr.stop());
    return true;
  } catch {
    return false;
  }
}

export type VoiceMode = "off" | "wake" | "command";

export function useVoiceRecognition(options: UseVoiceRecognitionOptions = {}) {
  const {
    wakeWord = DEFAULT_WAKE,
    lang = "es-ES",
    silenceTimeoutMs = 5000,
    commandMaxMs = 8000,
    wakeDebounceMs = 2500,
  } = options;

  const [supported] = useState(() => getCtor() !== null);
  const [mode, setMode] = useState<VoiceMode>("off");
  const [interim, setInterim] = useState("");

  /* Refs estables para callbacks (evita recrear el motor en cada render) */
  const cbRef = useRef(options);
  cbRef.current = options;

  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const modeRef = useRef<VoiceMode>("off");
  const lastWakeAtRef = useRef(0);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const maxTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wantActiveRef = useRef(false);
  const stoppedByUsRef = useRef(false);

  const setModeBoth = useCallback((m: VoiceMode) => {
    modeRef.current = m;
    setMode(m);
  }, []);

  const clearTimers = useCallback(() => {
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    if (maxTimerRef.current) clearTimeout(maxTimerRef.current);
    silenceTimerRef.current = null;
    maxTimerRef.current = null;
  }, []);

  /* ---------------- Motor único re-arrancable -------------------- */

  const buildRecognition = useCallback((): SpeechRecognitionLike | null => {
    const Ctor = getCtor();
    if (!Ctor) return null;
    const rec = new Ctor();
    rec.lang = lang;
    rec.continuous = true; // gestionamos nosotros los segmentos
    rec.interimResults = true;
    rec.maxAlternatives = 3;

    rec.onstart = () => cbRef.current.onStart?.();

    rec.onresult = (e) => {
      let finalText = "";
      let partialText = "";

      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        const txt = res[0]?.transcript ?? "";
        if (res.isFinal) finalText += txt;
        else partialText += txt;
      }

      const currentMode = modeRef.current;

      if (currentMode === "wake") {
        const candidate = `${finalText} ${partialText}`.trim();
        if (containsWake(candidate, wakeWord)) {
          const now = Date.now();
          // DEBOUNCE: ignora activaciones repetidas dentro de la ventana
          if (now - lastWakeAtRef.current < wakeDebounceMs) return;
          lastWakeAtRef.current = now;

          setInterim("");
          cbRef.current.onWake?.();
          // Pasar a captura de comando: reiniciar en modo command
          stoppedByUsRef.current = true;
          rec.abort(); // onend re-lanzará en modo command
          setModeBoth("command");
        }
        return;
      }

      if (currentMode === "command") {
        const live = `${finalText || ""}${partialText || ""}`.trim();
        if (live) {
          setInterim(live);
          cbRef.current.onInterim?.(live);
          // Resetear el timer de silencio con cada actualización
          if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
          silenceTimerRef.current = setTimeout(() => finish(live), silenceTimeoutMs);
        }
        if (finalText.trim()) {
          finish(finalText.trim());
        }
      }
    };

    rec.onerror = (e) => {
      const err = (e as Event & { error?: string }).error;
      if (err === "no-speech") {
        // En modo wake es normal (silencio ambiental): simplemente reinicia.
        if (modeRef.current === "command") cbRef.current.onError?.("no-speech");
        return;
      }
      if (err === "aborted" || err === "cancelled") {
        return; // provocado por nosotros al cambiar de modo
      }
      if (err === "not-allowed" || err === "service-not-allowed") {
        wantActiveRef.current = false;
        cbRef.current.onError?.("permission-denied");
        return;
      }
      if (err === "audio-capture") {
        wantActiveRef.current = false;
        cbRef.current.onError?.("no-mic");
        return;
      }
      if (err === "network") {
        cbRef.current.onError?.("network");
      }
    };

    rec.onend = () => {
      // El motor se detuvo (Chrome lo hace solo ~60s o al abortar).
      // Re-lanzar si el usuario sigue queriendo voz.
      if (!wantActiveRef.current) {
        setModeBoth("off");
        cbRef.current.onEnd?.();
        return;
      }
      // Si terminó un segmento de comando sin resultado final, cerrar con lo parcial
      if (modeRef.current === "command") {
        const pending = interimRef.current;
        clearTimers();
        if (pending) finish(pending);
        else {
          setInterim("");
          setModeBoth("wake");
        }
      }
      // Restart suave (pequeño delay para no saturar el servicio)
      try {
        setTimeout(() => {
          if (wantActiveRef.current) {
            stoppedByUsRef.current = false;
            rec.start();
          }
        }, 250);
      } catch {
        /* already started */
      }
    };

    return rec;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang, wakeWord, silenceTimeoutMs, wakeDebounceMs]);

  /* Ref espejo del interim para leerlo desde onend sin re-render */
  const interimRef = useRef("");
  useEffect(() => {
    interimRef.current = interim;
  }, [interim]);

  /** Cierra el comando actual: aplica timeout duro y entrega transcript */
  const finishRef = useRef<(text: string) => void>(() => {});
  finishRef.current = (text: string) => {
    clearTimers();
    const cmd = stripWake(text, wakeWord);
    setInterim("");
    setModeBoth("wake");
    if (cmd) cbRef.current.onCommand?.(cmd);
  };
  const finish = useCallback((text: string) => finishRef.current(text), []);

  /* Arrancar/cambiar timers duros cuando entramos en modo command */
  useEffect(() => {
    if (mode === "command") {
      maxTimerRef.current = setTimeout(() => {
        const pending = interimRef.current;
        if (pending) finish(pending);
        else {
          setInterim("");
          setModeBoth("wake");
          recRef.current?.abort();
        }
      }, commandMaxMs);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  /* ---------------- API pública ---------------------------------- */

  /** Activa el sistema de voz (wake word siempre escuchando). */
  const enable = useCallback(async (): Promise<boolean> => {
    if (!getCtor()) {
      cbRef.current.onError?.("unsupported");
      return false;
    }
    const ok = await requestMicPermission();
    if (!ok) {
      cbRef.current.onError?.("permission-denied");
      return false;
    }
    wantActiveRef.current = true;
    setModeBoth("wake");
    // Detener instancia previa si existiera
    try {
      recRef.current?.abort();
    } catch {
      /* noop */
    }
    const rec = buildRecognition();
    if (!rec) return false;
    recRef.current = rec;
    try {
      rec.start();
    } catch {
      /* start() puede lanzar si ya corría; onend re-lanzará */
    }
    return true;
  }, [buildRecognition, setModeBoth]);

  /** Desactiva todo el sistema de voz. */
  const disable = useCallback(() => {
    wantActiveRef.current = false;
    clearTimers();
    setInterim("");
    setModeBoth("off");
    try {
      recRef.current?.abort();
    } catch {
      /* noop */
    }
    recRef.current = null;
  }, [clearTimers, setModeBoth]);

  /** Forceja la escucha de un comando YA (botón del micrófono). */
  const captureCommandNow = useCallback(() => {
    if (!wantActiveRef.current) {
      void enable();
    }
    setModeBoth("command");
    setInterim("");
  }, [enable, setModeBoth]);

  const toggle = useCallback(() => {
    if (wantActiveRef.current) disable();
    else void enable();
  }, [disable, enable]);

  /* Cleanup al desmontar */
  useEffect(() => {
    return () => {
      wantActiveRef.current = false;
      clearTimers();
      try {
        recRef.current?.abort();
      } catch {
        /* noop */
      }
    };
  }, [clearTimers]);

  return {
    supported,
    mode,
    active: mode !== "off",
    interim,
    enable,
    disable,
    toggle,
    captureCommandNow,
  };
}
