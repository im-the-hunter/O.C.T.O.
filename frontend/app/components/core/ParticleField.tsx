"use client";

/**
 * ParticleField — Capa de partículas orbitando alrededor del núcleo.
 * Implementación en Canvas 2D (60fps vía requestAnimationFrame):
 *  - Partículas en órbitas elípticas con velocidades distintas
 *  - Estelas (trails) por desvanecimiento aditivo
 *  - Color ligado al estado actual de la IA
 */
import { useEffect, useRef } from "react";
import { STATE_COLORS, useJarvis, type JarvisState } from "@/lib/jarvis-state";

interface Particle {
  radius: number;   // distancia orbital normalizada (0..1)
  angle: number;    // ángulo actual
  speed: number;    // rad/segundo
  size: number;     // px
  alpha: number;
  ellipse: number;  // factor de achatamiento vertical
}

const PARTICLE_COUNT = 70;

function makeParticles(): Particle[] {
  return Array.from({ length: PARTICLE_COUNT }, () => ({
    radius: 0.35 + Math.random() * 0.6,
    angle: Math.random() * Math.PI * 2,
    speed: (0.08 + Math.random() * 0.3) * (Math.random() > 0.5 ? 1 : -1),
    size: 0.6 + Math.random() * 1.8,
    alpha: 0.25 + Math.random() * 0.6,
    ellipse: 0.55 + Math.random() * 0.4,
  }));
}

export default function ParticleField() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const colorRef = useRef<string>(STATE_COLORS.idle);
  const boostRef = useRef<number>(1); // multiplicador de velocidad según estado
  const { state } = useJarvis();

  // Sincroniza color/velocidad con el estado sin reiniciar el loop
  useEffect(() => {
    colorRef.current = STATE_COLORS[state];
    boostRef.current =
      state === "thinking" ? 3 : state === "listening" ? 1.6 : 1;
  }, [state]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const particles = makeParticles();
    let raf = 0;
    let last = performance.now();

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    const hexToRgb = (hex: string) => {
      const n = parseInt(hex.slice(1), 16);
      return `${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}`;
    };

    const draw = (now: number) => {
      const dt = Math.min((now - last) / 1000, 0.05);
      last = now;

      const w = window.innerWidth;
      const h = window.innerHeight;
      const cx = w / 2;
      const cy = h / 2;
      const scale = Math.min(w, h) * 0.48;

      // Trail: pintar fondo semitransparente en vez de limpiar
      ctx.fillStyle = "rgba(5, 5, 5, 0.18)";
      ctx.fillRect(0, 0, w, h);

      const rgb = hexToRgb(colorRef.current);
      for (const p of particles) {
        p.angle += p.speed * boostRef.current * dt;
        const x = cx + Math.cos(p.angle) * p.radius * scale;
        const y = cy + Math.sin(p.angle) * p.radius * scale * p.ellipse;

        ctx.beginPath();
        ctx.arc(x, y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${rgb}, ${p.alpha})`;
        ctx.shadowColor = `rgba(${rgb}, 0.8)`;
        ctx.shadowBlur = 6;
        ctx.fill();
        ctx.shadowBlur = 0;
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className="pointer-events-none fixed inset-0 z-0 h-full w-full"
    />
  );
}

// Re-exportar tipos usados por otros módulos si hiciera falta
export type { JarvisState };
