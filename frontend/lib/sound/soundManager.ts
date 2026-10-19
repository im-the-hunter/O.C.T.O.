import { Howl, Howler } from "howler";

/**
 * Motor de sonido del HUD basado en Howler.js (Fase 3).
 * Catálogo completo de SFX — los .mp3 viven en public/sounds/ y se
 * pueden regenerar con `python3 scripts/audio/generate_sounds.py`.
 * El ambient-hum (loop) lo gestiona <SoundProvider> directamente.
 */
const SOUNDS = {
  activationBeep: "/sounds/activation-beep.mp3", // wake word detectado
  thinking: "/sounds/thinking-sound.mp3", // mientras procesa (opcional)
  responseComplete: "/sounds/response-complete.mp3", // fin de respuesta
  buttonClick: "/sounds/button-click.mp3", // interacción con botones
  error: "/sounds/error-sound.mp3", // tono bajo de error
  hover: "/sounds/hover.mp3", // tick sutil al pasar el mouse
  messageIn: "/sounds/message-in.mp3", // mensaje entrante en el chat
} as const;

export type SoundName = keyof typeof SOUNDS;

class SoundManager {
  private cache: Partial<Record<SoundName, Howl>> = {};

  /** Precarga todos los SFX tras el primer gesto del usuario. */
  preload() {
    if (typeof window === "undefined") return;
    (Object.keys(SOUNDS) as SoundName[]).forEach((name) => {
      if (!this.cache[name]) {
        this.cache[name] = new Howl({
          src: [SOUNDS[name]],
          preload: true,
          volume: 1,
          html5: false, // WebAudio para latencia mínima
        });
      }
    });
  }

  play(name: SoundName, volume = 0.7) {
    if (typeof window === "undefined") return; // SSR-safe
    let howl = this.cache[name];
    if (!howl) {
      howl = new Howl({ src: [SOUNDS[name]], volume });
      this.cache[name] = howl;
    }
    howl.volume(volume);
    howl.play();
  }

  setMasterVolume(v: number) {
    Howler.volume(Math.min(1, Math.max(0, v)));
  }
}

export const soundManager = new SoundManager();
