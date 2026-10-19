"use client";

/**
 * VoiceController (Fase 3) — Orquesta el sistema de voz completo:
 *
 *   Wake word "JARVIS" (escucha continua) → beep de activación +
 *   núcleo en "listening" (naranja) → captura del comando con transcript
 *   en tiempo real → timeout de silencio 5 s → procesar:
 *     • comandos locales (silencio, modo oscuro/claro, pantalla completa,
 *       muestra el repositorio, estado del sistema) → sin LLM
 *     • cualquier otra cosa → se envía al chat como mensaje de usuario
 *   Respuesta de JARVIS → TTS (Web Speech / ElevenLabs) + núcleo en
 *   "speaking" con ondas expansivas sincronizadas + response-complete.
 *
 * Renderiza además la barra flotante de control de voz (toggle del
 * micrófono, indicador LISTENING y transcript parcial).
 */
import { useCallback, useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Mic, MicOff, Volume2, VolumeX } from "lucide-react";
import { useJarvis } from "@/lib/jarvis-state";
import { useSound } from "@/lib/sound/SoundManager";
import {
  useVoiceRecognition,
  type VoiceError,
} from "@/lib/voice/useVoiceRecognition";
import { useSpeechSynthesis } from "@/lib/voice/useSpeechSynthesis";

/* ------------------------------------------------------------------ */
/* Comandos locales (no requieren LLM)                                 */
/* ------------------------------------------------------------------ */

interface LocalCommand {
  /** patrones normalizados (minúsculas, sin tildes) */
  patterns: string[];
  run: (ctx: CommandContext) => string | null; // respuesta hablada o null
}

interface CommandContext {
  toggleMute: () => void;
  setMuted: (m: boolean) => void;
  muted: boolean;
  addMessage: (role: "user" | "jarvis", content: string) => void;
  setMetricsPatch: (patch: Record<string, unknown>) => void;
  repoName: string;
  metricsSummary: () => string;
}

const normalize = (s: string) =>
  s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim();

const LOCAL_COMMANDS: LocalCommand[] = [
  {
    patterns: ["silencio", "mute", "calate", "shutup", "shut up", "sin sonido"],
    run: (c) => {
      c.toggleMute();
      return c.muted
        ? "Sonido restaurado, señor."
        : "Silencio activado. Quedo a la espera.";
    },
  },
  {
    patterns: ["modo claro", "light mode", "cambia a claro"],
    run: (c) => {
      document.documentElement.classList.add("theme-light");
      c.addMessage("jarvis", "Modo claro activado.");
      return null; // ya respondió por chat; evita doble habla
    },
  },
  {
    patterns: ["modo oscuro", "dark mode", "cambia a oscuro"],
    run: (c) => {
      document.documentElement.classList.remove("theme-light");
      c.addMessage("jarvis", "De vuelta al modo oscuro. Una elección sensata.");
      return null;
    },
  },
  {
    patterns: ["pantalla completa", "fullscreen", "full screen"],
    run: () => {
      if (document.fullscreenElement) {
        void document.exitFullscreen();
        return "Modo pantalla completa desactivado.";
      }
      void document.documentElement.requestFullscreen().catch(() => {});
      return "Modo pantalla completa activado.";
    },
  },
  {
    patterns: [
      "muestra el repositorio",
      "abre el repositorio",
      "repo",
      "repository",
      "grafo del repo",
      "show the repository",
    ],
    run: (c) => {
      window.dispatchEvent(new CustomEvent("jarvis:open-repo"));
      c.setMetricsPatch({}); // no-op defensivo
      return `Abriendo el grafo del repositorio ${c.repoName}, señor.`;
    },
  },
  {
    patterns: [
      "estado del sistema",
      "sistema",
      "system status",
      "diagnostico",
      "diagnostic",
      "cómo estás",
      "como estas",
    ],
    run: (c) => c.metricsSummary(),
  },
];

/* ------------------------------------------------------------------ */
/* Componente                                                          */
/* ------------------------------------------------------------------ */

export default function VoiceController() {
  const {
    setState,
    addMessage,
    bumpTokens,
    setVoiceInterim,
    voiceActive,
    setVoiceActive,
    voiceError,
    setVoiceError,
    pendingSpeech,
    setPendingSpeech,
    metrics,
    setMetrics,
    state,
  } = useJarvis();

  const sfx = useSound();

  /* --- TTS ---------------------------------------------------------- */
  const tts = useSpeechSynthesis({ rate: 1.0, pitch: 1.0, volume: 0.8 });

  /* Publicar el motor TTS activo para la telemetría del HUD */
  useEffect(() => {
    (window as unknown as {
      __jarvisTts?: { engine: string; voiceName: string | null };
    }).__jarvisTts = {
      engine: sfx.elevenLabsEnabled ? "elevenlabs" : "native",
      voiceName: tts.voiceName,
    };
  }, [tts.voiceName, sfx.elevenLabsEnabled]);

  /* Mantener última pregunta para reintentos futuros (Fase 4 usará esto) */
  const lastQueryRef = useRef("");

  const speakResponse = useCallback(
    (text: string) => {
      addMessage("jarvis", text);
      bumpTokens(text);
      setPendingSpeech(text);
    },
    [addMessage, bumpTokens, setPendingSpeech]
  );

  /* Hablar cuando pendingSpeech cambie (desde chat o desde voz) */
  useEffect(() => {
    if (!pendingSpeech) return;
    const text = pendingSpeech;
    setPendingSpeech(null);
    sfx.play("thinking", 0.35);
    // pequeña pausa dramática estilo JARVIS antes de responder
    const id = setTimeout(() => {
      void tts.speak(text);
    }, 350);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingSpeech]);

  /* Sincronizar estado del núcleo con el TTS */
  useEffect(() => {
    tts.setCallbacks({
      onStart: () => setState("speaking"),
      onDone: () => {
        setState("idle");
        sfx.play("responseComplete", 0.6);
      },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* Si JARVIS está hablando y llega un nuevo "silencio", cancela */
  useEffect(() => {
    if (tts.speaking && state !== "speaking") tts.cancel();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  /* --- Errores de voz → HUD + sonido -------------------------------- */
  const ERROR_MESSAGES: Record<VoiceError, string | null> = {
    unsupported:
      "Tu navegador no soporta reconocimiento de voz. Usa Chrome o Edge.",
    "permission-denied":
      "Acceso al micrófono denegado. Habilítalo en los permisos del navegador.",
    "no-mic": "No se detecta ningún micrófono en el sistema.",
    "no-speech": "Lo siento, no pude entender eso.",
    network: "Error de red en el servicio de reconocimiento de voz.",
    aborted: null,
  };

  const handleVoiceError = useCallback(
    (err: VoiceError) => {
      const msg = ERROR_MESSAGES[err];
      if (!msg) return;
      setVoiceError(msg);
      sfx.play("error", 0.5);
      // Auto-ocultar tras 4 s
      setTimeout(() => setVoiceError(null), 4000);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [setVoiceError, sfx]
  );

  /* --- Procesamiento del comando ----------------------------------- */
  const processCommand = useCallback(
    (raw: string) => {
      const cmd = normalize(raw);
      lastQueryRef.current = raw;
      setVoiceInterim("");

      // 1) ¿Comando local?
      const local = LOCAL_COMMANDS.find((lc) =>
        lc.patterns.some((p) => cmd.includes(p))
      );
      if (local) {
        addMessage("user", raw);
        bumpTokens(raw);
        const reply = local.run({
          toggleMute: sfx.toggleMute,
          setMuted: sfx.setMuted,
          muted: sfx.muted,
          addMessage,
          setMetricsPatch: (patch) => setMetrics((m) => ({ ...m, ...patch })),
          repoName: metrics.repoName,
          metricsSummary: () =>
            `Diagnóstico del sistema: CPU al ${metrics.cpu}%, memoria al ${metrics.memory}%. ` +
            `Base vectorial ${metrics.vectorDbConnected ? "conectada" : "sin conexión"}. ` +
            `Repositorio ${metrics.repoName} sincronizado en la rama ${metrics.branch}. ` +
            `Pipeline ${metrics.ciGreen ? "en verde" : "con fallos"}. Todo bajo control, señor.`,
        });
        if (reply) speakResponse(reply);
        return;
      }

      // 2) Cualquier otro asunto → canal de chat (mock LLM / Fase 4 backend)
      setVoiceInterim("");
      addMessage("user", raw);
      bumpTokens(raw);
      setState("thinking");
      sfx.play("thinking", 0.35);
      setTimeout(() => {
        speakResponse(
          `He recibido su instrucción por voz: "${raw}". El agente RAG se conectará en la próxima fase, señor.`
        );
      }, 900);
    },
    [
      addMessage,
      bumpTokens,
      metrics,
      sfx,
      setMetrics,
      setState,
      setVoiceInterim,
      speakResponse,
    ]
  );

  /* --- Reconocimiento + wake word ------------------------------------ */
  const voice = useVoiceRecognition({
    wakeWord: "jarvis",
    lang: "es-ES",
    silenceTimeoutMs: 5000,
    commandMaxMs: 8000,
    wakeDebounceMs: 2500,
    onWake: () => {
      // Beep suave + núcleo naranja "listening"
      sfx.play("activationBeep", 0.7);
      setState("listening");
    },
    onInterim: (text) => setVoiceInterim(text),
    onCommand: (transcript) => {
      setState("thinking");
      processCommand(transcript);
    },
    onError: handleVoiceError,
  });

  /* Reflejar actividad de voz en el contexto global */
  useEffect(() => {
    setVoiceActive(voice.active);
  }, [voice.active, setVoiceActive]);

  /* Volver a "idle" si estaba listening pero la escucha de comando terminó
     sin resultado (timeout de silencio vacío) */
  useEffect(() => {
    if (state === "listening" && voice.mode !== "command" && !voice.active) {
      setState("idle");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voice.mode, voice.active]);

  /* Atajos de teclado: Ctrl+Shift+Space alterna voz, Escape cancela habla */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.code === "Space") {
        e.preventDefault();
        voice.toggle();
      }
      if (e.key === "Escape" && tts.speaking) tts.cancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tts.speaking]);

  /* Precargar SFX tras el primer gesto (lo hace SoundProvider también) */
  useEffect(() => {
    const unlock = () => sfx.play("hover", 0.001); // init silencioso de Howler
    window.addEventListener("pointerdown", unlock, { once: true });
    return () => window.removeEventListener("pointerdown", unlock);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const micOn = voice.mode === "command";
  const wakeOn = voice.mode === "wake";

  return (
    <>
      {/* ---------- Barra flotante de control de voz ---------- */}
      <div className="pointer-events-auto fixed bottom-20 left-1/2 z-[60] -translate-x-1/2 lg:bottom-8">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-3 border border-jarvis/25 bg-black/60 px-4 py-2 backdrop-blur-md"
          style={{
            clipPath:
              "polygon(10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%, 0 10px)",
          }}
        >
          {/* Toggle micrófono (manual) */}
          <button
            onClick={() => {
              sfx.play("buttonClick", 0.5);
              voice.toggle();
            }}
            aria-label={voice.active ? "Desactivar voz" : "Activar voz"}
            title={`${voice.active ? "Desactivar" : "Activar"} voz (Ctrl+Shift+Espacio)`}
            className={`relative flex h-9 w-9 items-center justify-center rounded-full border transition-colors ${
              voice.active
                ? "border-jarvis/70 bg-jarvis/10 text-jarvis"
                : "border-white/20 bg-white/5 text-white/40 hover:text-white/70"
            }`}
          >
            {voice.supported ? (
              voice.active ? (
                <Mic size={16} />
              ) : (
                <MicOff size={16} />
              )
            ) : (
              <MicOff size={16} />
            )}
            {micOn && (
              <span className="absolute inset-0 animate-ping rounded-full border border-alert-warn/60" />
            )}
          </button>

          {/* Estado textual */}
          <div className="min-w-[190px] font-tech text-[10px] uppercase tracking-widest md:text-xs">
            {!voice.supported ? (
              <span className="text-alert-warn">Voz no soportada — usa Chrome/Edge</span>
            ) : micOn ? (
              <span className="text-listening">
                ◉ Escuchando comando…
                <AnimatePresence>
                  {voice.interim && (
                    <motion.span
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="ml-2 normal-case tracking-normal text-white/80"
                    >
                      “{voice.interim}”
                    </motion.span>
                  )}
                </AnimatePresence>
              </span>
            ) : wakeOn ? (
              <span className="text-jarvis/80">◇ En espera — di «J.A.R.V.I.S.»</span>
            ) : (
              <span className="text-white/35">Micrófono inactivo</span>
            )}
          </div>

          {/* Toggle mute global */}
          <button
            onClick={() => {
              sfx.play("buttonClick", 0.5);
              sfx.toggleMute();
            }}
            aria-label={sfx.muted ? "Quitar silencio" : "Silenciar"}
            title={sfx.muted ? "Reactivar sonido (o di «JARVIS silencio»)" : "Silenciar (o di «JARVIS silencio»)"}
            className={`flex h-9 w-9 items-center justify-center rounded-full border transition-colors ${
              sfx.muted
                ? "border-alert-warn/60 bg-alert-warn/10 text-alert-warn"
                : "border-jarvis/40 text-jarvis/80 hover:text-jarvis"
            }`}
          >
            {sfx.muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
          </button>
        </motion.div>
      </div>

      {/* ---------- Banner de error de voz en el HUD ---------- */}
      <AnimatePresence>
        {voiceError && (
          <motion.div
            initial={{ opacity: 0, y: -16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -16 }}
            className="pointer-events-none fixed left-1/2 top-20 z-[70] -translate-x-1/2 border border-alert-warn/60 bg-black/80 px-5 py-2 backdrop-blur-md"
          >
            <p className="font-tech text-xs uppercase tracking-widest text-alert-warn text-glow-red">
              ⚠ {voiceError}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
