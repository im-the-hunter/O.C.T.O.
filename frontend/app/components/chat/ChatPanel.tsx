"use client";

/**
 * ChatPanel — Terminal de conversación con efecto typewriter.
 *  - Mensajes de usuario: cian, alineados a la derecha
 *  - Mensajes de JARVIS: blanco, alineados a la izquierda (typewriter)
 *  - Scroll automático al último mensaje
 *  - Input: "Ask JARVIS anything..."
 *
 * Simulación local de respuesta (Fase 3 conectará /backend/api/ai).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import HudPanel from "@/components/ui/HudPanel";
import { useJarvis, type ChatMessage } from "@/lib/jarvis-state";

/* ------------------------------------------------------------------ */
/* Typewriter                                                         */
/* ------------------------------------------------------------------ */

function TypewriterText({ text, done }: { text: string; done?: () => void }) {
  const [shown, setShown] = useState(0);

  useEffect(() => {
    setShown(0);
    const id = setInterval(() => {
      setShown((s) => {
        if (s >= text.length) {
          clearInterval(id);
          done?.();
          return s;
        }
        return s + 1;
      });
    }, 18); // ~55 chars/s
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  return (
    <span>
      {text.slice(0, shown)}
      {shown < text.length && (
        <span className="ml-0.5 inline-block h-3 w-1.5 animate-jarvis-blink bg-white align-middle" />
      )}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Burbuja de mensaje                                                  */
/* ------------------------------------------------------------------ */

function MessageRow({ msg, isLastJarvis, onDone }: {
  msg: ChatMessage;
  isLastJarvis: boolean;
  onDone: () => void;
}) {
  const isUser = msg.role === "user";
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={`flex ${isUser ? "justify-end" : "justify-start"}`}
    >
      <div
        className={`max-w-[85%] border px-3 py-2 font-tech text-xs leading-relaxed md:text-sm ${
          isUser
            ? "border-jarvis/40 bg-jarvis/5 text-jarvis"
            : "border-white/15 bg-white/5 text-white"
        }`}
        style={{
          clipPath: isUser
            ? "polygon(0 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%)"
            : "polygon(8px 0, 100% 0, 100% 100%, 0 100%, 0 8px)",
        }}
      >
        <span className="mr-2 text-[9px] uppercase tracking-widest opacity-50">
          {isUser ? "TÚ" : "JARVIS"}
        </span>
        {isUser || !isLastJarvis ? (
          msg.content
        ) : (
          <TypewriterText text={msg.content} done={onDone} />
        )}
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/* Respuestas simuladas (Fase 3: reemplazar por llamada al backend)   */
/* ------------------------------------------------------------------ */

const CANNED: string[] = [
  "Analicé el repositorio, señor. Todo parece en orden... por ahora.",
  "He indexado 142 módulos en la base vectorial. El tiempo de recuperación es de 38 ms.",
  "Esa solicitud requerirá acceso al pipeline de CI. ¿Desea que continúe?",
  "Según los registros, el último despliegue fue exitoso. Sin anomalías detectadas.",
  "Por supuesto, señor. Procedo con la optimización solicitada.",
];

export default function ChatPanel() {
  const { messages, addMessage, setState, bumpTokens, setPendingSpeech, voiceInterim, state } =
    useJarvis();
  const [input, setInput] = useState("");
  const [typingId, setTypingId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const replyIdx = useRef(0);

  /* Scroll automático al último mensaje */
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, typingId]);

  const send = useCallback(() => {
    const text = input.trim();
    if (!text) return;
    setInput("");
    addMessage("user", text);
    bumpTokens(text);
    setState("thinking");

    // Simula latencia del agente RAG → luego "habla" la respuesta.
    // pendingSpeech hace que VoiceController la pronuncie con TTS
    // (Fase 3: el habla y el typewriter comparten el mismo texto).
    setTimeout(() => {
      const reply = CANNED[replyIdx.current % CANNED.length];
      replyIdx.current += 1;
      const id = `jarvis-${Date.now()}`;
      setState("speaking");
      addMessage("jarvis", reply);
      bumpTokens(reply);
      setTypingId(id);
      setPendingSpeech(reply);
    }, 900);
  }, [input, addMessage, setState, bumpTokens, setPendingSpeech]);

  const lastMsg = messages[messages.length - 1];
  const isTypingDone = typingId !== null && lastMsg?.role === "jarvis";

  return (
    <HudPanel title="Canal de Comunicación" className="flex h-full flex-col">
      {/* ---------- Historial ---------- */}
      <div
        ref={scrollRef}
        className="flex-1 space-y-3 overflow-y-auto px-3 py-3"
      >
        {messages.map((m) => (
          <MessageRow
            key={m.id}
            msg={m}
            isLastJarvis={isTypingDone && m.id === lastMsg.id}
            onDone={() => {
              setTypingId(null);
              setState("idle");
            }}
          />
        ))}
        {lastMsg?.role === "user" && (
          <div className="flex justify-start">
            <span className="animate-jarvis-flicker font-tech text-xs text-holo-light">
              ▍ JARVIS está procesando…
            </span>
          </div>
        )}

        {/* Fase 3: transcript del micrófono en tiempo real */}
        {state === "listening" && voiceInterim && (
          <div className="flex justify-end">
            <span className="max-w-[85%] border border-listening/40 bg-listening/5 px-3 py-2 font-tech text-xs text-listening">
              <span className="mr-2 text-[9px] uppercase tracking-widest opacity-60">
                🎙 Voz
              </span>
              {voiceInterim}
              <span className="ml-1 inline-block h-3 w-1.5 animate-jarvis-blink bg-listening align-middle" />
            </span>
          </div>
        )}
      </div>

      {/* ---------- Input ---------- */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="flex items-center gap-2 border-t border-jarvis/15 px-3 py-2"
      >
        <span className="font-tech text-sm text-system-ok">&gt;</span>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask JARVIS anything..."
          spellCheck={false}
          className="flex-1 bg-transparent font-tech text-xs text-white caret-jarvis outline-none placeholder:text-jarvis/40 md:text-sm"
        />
        <button
          type="submit"
          className="hud-button scale-90 px-3 py-1"
          aria-label="Enviar mensaje"
        >
          Transmitir
        </button>
      </form>
    </HudPanel>
  );
}
