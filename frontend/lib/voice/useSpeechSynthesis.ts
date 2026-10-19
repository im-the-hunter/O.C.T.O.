"use client";

/**
 * useSpeechSynthesis (Fase 3) — Voz de J.A.R.V.I.S.
 *
 * Motor primario: Web Speech API (speechSynthesis), buscando la voz más
 * "british mayordomo" disponible: Google UK English Male, Daniel,
 * Microsoft Ryan/Sonny… con rate 1.0, pitch 1.0, volume 0.8.
 *
 * Motor premium opcional: ElevenLabs. Si NEXT_PUBLIC_ELEVENLABS_API_KEY
 * está definida, speak() pide el audio a la API y lo reproduce con un
 * <audio>; si falla, cae de vuelta a speechSynthesis.
 *
 * Expone callbacks onStart/onBoundary/onDone para que VoiceController
 * sincronice el estado del núcleo ("speaking") y las ondas expansivas.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export interface JarvisVoiceSettings {
  rate?: number; // 1.0 velocidad normal
  pitch?: number; // 1.0 tono normal
  volume?: number; // 0.8 por defecto
  lang?: string; // "en-GB" preferido para el acento de JARVIS
}

/** Voces masculinas británicas típicas en Chrome/Edge/Safari/macOS */
const PREFERRED_VOICES = [
  "google uk english male",
  "daniel",
  "microsoft ryan online (natural) - en-gb",
  "microsoft ryanaudio2 - en-gb",
  "sonny",
  "arthur",
  "oliver",
  "microsoft george - en-gb",
  "en-gb male",
];

function pickEnglishVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  if (!voices.length) return null;
  const lower = (v: SpeechSynthesisVoice) => v.name.toLowerCase();
  for (const pref of PREFERRED_VOICES) {
    const hit = voices.find((v) => lower(v).includes(pref));
    if (hit) return hit;
  }
  // fallback: cualquier en-GB, luego cualquier inglés
  return (
    voices.find((v) => v.lang.startsWith("en-GB")) ??
    voices.find((v) => v.lang.startsWith("en")) ??
    voices[0]
  );
}

export function useSpeechSynthesis(settings: JarvisVoiceSettings = {}) {
  const { rate = 1.0, pitch = 1.0, volume = 0.8, lang = "en-GB" } = settings;

  const [speaking, setSpeaking] = useState(false);
  const [voiceName, setVoiceName] = useState<string | null>(null);
  const [elevenLabsActive, setElevenLabsActive] = useState(false);

  const voiceRef = useRef<SpeechSynthesisVoice | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const cbsRef = useRef<{
    onStart?: () => void;
    onBoundary?: (charIndex: number) => void;
    onDone?: () => void;
  }>({});
  const supported = typeof window !== "undefined" && "speechSynthesis" in window;

  /* Cargar voces (llegan async en Chrome) */
  useEffect(() => {
    if (!supported) return;
    const load = () => {
      const v = pickEnglishVoice(window.speechSynthesis.getVoices());
      if (v) {
        voiceRef.current = v;
        setVoiceName(v.name);
      }
    };
    load();
    window.speechSynthesis.addEventListener("voiceschanged", load);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", load);
  }, [supported]);

  /* Cleanup al desmontar */
  useEffect(() => {
    return () => {
      if (supported) window.speechSynthesis.cancel();
      audioRef.current?.pause();
      audioRef.current = null;
    };
  }, [supported]);

  /** Habla nativa (speechSynthesis) */
  const speakNative = useCallback(
    (text: string) => {
      if (!supported || !text) return;
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      if (voiceRef.current) u.voice = voiceRef.current;
      u.lang = voiceRef.current?.lang ?? lang;
      u.rate = rate;
      u.pitch = pitch;
      u.volume = volume;
      u.onstart = () => {
        setSpeaking(true);
        cbsRef.current.onStart?.();
      };
      u.onboundary = (e) => cbsRef.current.onBoundary?.(e.charIndex);
      u.onend = () => {
        setSpeaking(false);
        cbsRef.current.onDone?.();
      };
      u.onerror = () => {
        setSpeaking(false);
        cbsRef.current.onDone?.();
      };
      window.speechSynthesis.speak(u);
    },
    [supported, lang, rate, pitch, volume]
  );

  /** ElevenLabs: genera MP3 y lo reproduce; cae a nativa si falla */
  const speakElevenLabs = useCallback(
    async (text: string): Promise<boolean> => {
      const key = process.env.NEXT_PUBLIC_ELEVENLABS_API_KEY;
      const voiceId = process.env.NEXT_PUBLIC_ELEVENLABS_VOICE_ID ?? "pNInz6obpgDQGcFmaJgB"; // "Daniel"
      if (!key) return false;
      try {
        const res = await fetch(
          `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}`,
          {
            method: "POST",
            headers: {
              "xi-api-key": key,
              "Content-Type": "application/json",
              Accept: "audio/mpeg",
            },
            body: JSON.stringify({
              text,
              model_id: "eleven_turbo_v2_5",
              voice_settings: { stability: 0.5, similarity_boost: 0.75 },
            }),
          }
        );
        if (!res.ok) throw new Error(`ElevenLabs HTTP ${res.status}`);
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const audio = audioRef.current ?? new Audio();
        audioRef.current = audio;
        audio.src = url;
        audio.volume = volume;
        setSpeaking(true);
        setElevenLabsActive(true);
        cbsRef.current.onStart?.();
        await audio.play();
        audio.onended = () => {
          URL.revokeObjectURL(url);
          setSpeaking(false);
          cbsRef.current.onDone?.();
        };
        return true;
      } catch {
        setElevenLabsActive(false);
        return false; // el llamador usará speakNative
      }
    },
    [volume]
  );

  /** API principal: intenta ElevenLabs, fallback nativo */
  const speak = useCallback(
    async (text: string) => {
      const ok = await speakElevenLabs(text);
      if (!ok) speakNative(text);
    },
    [speakElevenLabs, speakNative]
  );

  const cancel = useCallback(() => {
    if (supported) window.speechSynthesis.cancel();
    audioRef.current?.pause();
    setSpeaking(false);
  }, [supported]);

  const setCallbacks = useCallback(
    (cb: { onStart?: () => void; onBoundary?: (i: number) => void; onDone?: () => void }) => {
      cbsRef.current = cb;
    },
    []
  );

  return {
    supported,
    speaking,
    voiceName,
    elevenLabsActive,
    speak,
    cancel,
    setCallbacks,
  };
}
