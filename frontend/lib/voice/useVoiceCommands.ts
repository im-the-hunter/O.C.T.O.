"use client";

import { useCallback, useRef, useState } from "react";

type SpeechRecognitionType = any; // Web Speech API (no tipada oficialmente)

/**
 * Hook de comandos de voz (Web Speech API).
 * FASE 1: esqueleto — la integración con J.A.R.V.I.S. llega en Fase 4.
 */
export function useVoiceCommands(onCommand?: (transcript: string) => void) {
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionType | null>(null);

  const start = useCallback(() => {
    if (typeof window === "undefined") return;
    const SR =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;
    if (!SR) return console.warn("Web Speech API no soportada en este navegador.");

    const recognition = new SR();
    recognition.lang = "es-ES";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onresult = (e: any) =>
      onCommand?.(e.results[0][0].transcript.trim());
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  }, [onCommand]);

  const stop = useCallback(() => recognitionRef.current?.stop(), []);

  return { listening, start, stop };
}
