import { Howl, Howler } from "howler";

/**
 * Sistema de sonido del HUD basado en Howler.js.
 * FASE 1: esqueleto. Los archivos se colocan en public/sounds/.
 */
const SOUNDS = {
  boot: "/sounds/boot.mp3",
  hover: "/sounds/hover.mp3",
  click: "/sounds/click.mp3",
  messageIn: "/sounds/message_in.mp3",
  jarvisSpeak: "/sounds/jarvis_speak.mp3",
  alert: "/sounds/alert.mp3",
} as const;

export type SoundName = keyof typeof SOUNDS;

class SoundManager {
  private cache: Partial<Record<SoundName, Howl>> = {};

  play(name: SoundName, volume = 0.7) {
    if (typeof window === "undefined") return; // SSR-safe
    let howl = this.cache[name];
    if (!howl) {
      howl = new Howl({ src: [SOUNDS[name]], volume });
      this.cache[name] = howl;
    }
    howl.play();
  }

  setMasterVolume(v: number) {
    Howler.volume(Math.min(1, Math.max(0, v)));
  }
}

export const soundManager = new SoundManager();
