"use client";

/**
 * Estado global del asistente J.A.R.V.I.S.
 * Patrón "atom" ligero: un único contexto con el estado de la IA,
 * la conversación y las métricas del HUD. Los componentes se
 * re-suscriben vía useContext; los hijos pesados (JarvisCore) memoizan
 * para mantener 60fps.
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

/* ------------------------------------------------------------------ */
/* Tipos                                                              */
/* ------------------------------------------------------------------ */

export type JarvisState = "idle" | "listening" | "thinking" | "speaking";

export interface ChatMessage {
  id: string;
  role: "user" | "jarvis";
  content: string;
  timestamp: number;
}

export interface HudMetrics {
  cpu: number; // %
  memory: number; // %
  contextTokens: number;
  repoName: string;
  lastCommit: string;
  branch: string;
  ciGreen: boolean;
  vectorDbConnected: boolean;
}

interface JarvisContextValue {
  state: JarvisState;
  setState: (s: JarvisState) => void;
  messages: ChatMessage[];
  addMessage: (role: ChatMessage["role"], content: string) => void;
  metrics: HudMetrics;
  setMetrics: React.Dispatch<React.SetStateAction<HudMetrics>>;
  /** Incrementa tokens de contexto según el tamaño del último mensaje */
  bumpTokens: (text: string) => void;
}

const JarvisContext = createContext<JarvisContextValue | null>(null);

/* ------------------------------------------------------------------ */
/* Provider                                                           */
/* ------------------------------------------------------------------ */

const INITIAL_MESSAGES: ChatMessage[] = [
  {
    id: "boot",
    role: "jarvis",
    content:
      "Sistemas en línea. J.A.R.V.I.S. v2.0 operativo. ¿En qué puedo ayudarle, señor?",
    timestamp: Date.now(),
  },
];

export function JarvisProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<JarvisState>("idle");
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const [metrics, setMetrics] = useState<HudMetrics>({
    cpu: 12,
    memory: 34,
    contextTokens: 512,
    repoName: "project-jarvis",
    lastCommit: "hace 2 min",
    branch: "main",
    ciGreen: true,
    vectorDbConnected: true,
  });
  const idRef = useRef(0);

  const addMessage = useCallback(
    (role: ChatMessage["role"], content: string) => {
      idRef.current += 1;
      setMessages((prev) => [
        ...prev,
        { id: `msg-${idRef.current}`, role, content, timestamp: Date.now() },
      ]);
    },
    []
  );

  const bumpTokens = useCallback((text: string) => {
    // Aproximación barata: ~4 chars por token.
    const approx = Math.ceil(text.length / 4);
    setMetrics((m) => ({ ...m, contextTokens: m.contextTokens + approx }));
  }, []);

  const value = useMemo(
    () => ({
      state,
      setState,
      messages,
      addMessage,
      metrics,
      setMetrics,
      bumpTokens,
    }),
    [state, messages, addMessage, metrics, bumpTokens]
  );

  return (
    <JarvisContext.Provider value={value}>{children}</JarvisContext.Provider>
  );
}

export function useJarvis(): JarvisContextValue {
  const ctx = useContext(JarvisContext);
  if (!ctx) throw new Error("useJarvis debe usarse dentro de <JarvisProvider>");
  return ctx;
}

/* ------------------------------------------------------------------ */
/* Paleta de colores por estado (compartida por Core y HUD)           */
/* ------------------------------------------------------------------ */

export const STATE_COLORS: Record<JarvisState, string> = {
  idle: "#00f3ff",
  listening: "#ff6b00",
  thinking: "#ffffff",
  speaking: "#00f3ff",
};
