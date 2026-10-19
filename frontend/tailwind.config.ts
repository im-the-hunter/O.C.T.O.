import type { Config } from "tailwindcss";

/**
 * Project J.A.R.V.I.S. — Tema sci-fi / HUD estilo Iron Man
 * Paleta: cian neón, azul profundo, violeta holográfico, acentos ámbar/alerta.
 */
const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Fondo principal: negro espacial con tinte azul
        void: {
          DEFAULT: "#030b14",
          deep: "#02060d",
          panel: "#071523",
        },
        // Cian neón (color primario del HUD)
        jarvis: {
          DEFAULT: "#00e5ff",
          light: "#7df9ff",
          bright: "#22d3ee",
          dim: "#0e7490",
          glow: "rgba(0, 229, 255, 0.35)",
        },
        // Azul profundo (superficies y bordes)
        abyss: {
          DEFAULT: "#0a1e3f",
          light: "#12345e",
          border: "#1b4a7a",
        },
        // Violeta holográfico (secundario / IA thinking)
        holo: {
          DEFAULT: "#8b5cf6",
          light: "#c4b5fd",
          glow: "rgba(139, 92, 246, 0.35)",
        },
        // Verde sistema (status OK)
        system: {
          ok: "#00ff9d",
          idle: "#38bdf8",
        },
        // Ámbar / alerta (warnings de Tony Stark)
        alert: {
          warn: "#ffb347",
          critical: "#ff3b5c",
        },
      },
      fontFamily: {
        hud: ["var(--font-orbitron)", "monospace"],
        mono: ["var(--font-jetbrains)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        "glow-cyan": "0 0 10px rgba(0,229,255,0.5), 0 0 30px rgba(0,229,255,0.25)",
        "glow-cyan-lg": "0 0 20px rgba(0,229,255,0.6), 0 0 60px rgba(0,229,255,0.35)",
        "glow-violet": "0 0 10px rgba(139,92,246,0.5), 0 0 30px rgba(139,92,246,0.25)",
        "glow-red": "0 0 10px rgba(255,59,92,0.6), 0 0 30px rgba(255,59,92,0.3)",
        "inner-panel": "inset 0 0 20px rgba(0,229,255,0.08)",
      },
      borderColor: {
        hud: "#1b4a7a",
      },
      backgroundImage: {
        "hud-grid":
          "linear-gradient(rgba(0,229,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(0,229,255,0.05) 1px, transparent 1px)",
        "radar-sweep":
          "conic-gradient(from 0deg, transparent 0deg, rgba(0,229,255,0.25) 60deg, transparent 90deg)",
        "arc-reactor":
          "radial-gradient(circle at center, rgba(0,229,255,0.9) 0%, rgba(0,229,255,0.3) 40%, transparent 70%)",
      },
      backgroundSize: {
        grid: "40px 40px",
      },
      keyframes: {
        pulseGlow: {
          "0%, 100%": { opacity: "1", filter: "drop-shadow(0 0 6px rgba(0,229,255,0.8))" },
          "50%": { opacity: "0.6", filter: "drop-shadow(0 0 16px rgba(0,229,255,0.4))" },
        },
        radarSweep: {
          from: { transform: "rotate(0deg)" },
          to: { transform: "rotate(360deg)" },
        },
        flicker: {
          "0%, 100%": { opacity: "1" },
          "92%": { opacity: "1" },
          "93%": { opacity: "0.4" },
          "94%": { opacity: "1" },
          "97%": { opacity: "0.7" },
          "98%": { opacity: "1" },
        },
        scanline: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100vh)" },
        },
        spinSlow: {
          from: { transform: "rotate(0deg)" },
          to: { transform: "rotate(360deg)" },
        },
        spinReverse: {
          from: { transform: "rotate(360deg)" },
          to: { transform: "rotate(0deg)" },
        },
      },
      animation: {
        "pulse-glow": "pulseGlow 2.4s ease-in-out infinite",
        "radar-sweep": "radarSweep 4s linear infinite",
        flicker: "flicker 6s linear infinite",
        scanline: "scanline 8s linear infinite",
        "spin-slow": "spinSlow 12s linear infinite",
        "spin-reverse": "spinReverse 8s linear infinite",
      },
      spacing: {
        hud: "clamp(0.5rem, 1vw, 1rem)",
      },
    },
  },
  plugins: [],
};

export default config;
