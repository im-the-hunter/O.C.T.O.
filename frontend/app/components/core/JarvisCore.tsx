"use client";

/**
 * JarvisCore — Núcleo SVG de J.A.R.V.I.S. ("arc reactor")
 *
 * 5 círculos concéntricos (viewBox 600x600, centro 300,300):
 *  1. Estado      r=80   stroke 2   color según estado + glow intenso
 *  2. Datos       r=120  stroke 8   #0066ff, dash "20 10", rotación horaria 60s
 *  3. Discontinuo r=160  stroke 3   #00f3ff op 0.6, dash "5 15", antihorario 45s
 *  4. Radar       r=200  stroke 12  #0044aa op 0.3, pulso de opacidad 4s
 *  5. Contención  r=240  stroke 1   blanco op 0.2, estático
 *
 * Efectos:
 *  - Framer Motion: ondas expansivas cuando state === "speaking"
 *  - GSAP: animaciones SVG precisas (pulso del círculo 1, glow dinámico)
 *  - Gradientes radiales para el plasma interior
 */
import { memo, useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import gsap from "gsap";
import { useJarvis, type JarvisState } from "@/lib/jarvis-state";

/* ------------------------------------------------------------------ */
/* Configuración por estado                                           */
/* ------------------------------------------------------------------ */

interface StateConfig {
  color: string;
  /** duración (s) del pulso de escala del círculo interno */
  pulseDuration: number;
  /** velocidad extra de rotación del anillo de datos */
  spinBoost: number;
}

const STATE_CONFIG: Record<JarvisState, StateConfig> = {
  idle: { color: "#00f3ff", pulseDuration: 2, spinBoost: 0 },
  listening: { color: "#ff6b00", pulseDuration: 0.5, spinBoost: 0 },
  thinking: { color: "#ffffff", pulseDuration: 1, spinBoost: 8 }, // rotación rápida
  speaking: { color: "#00f3ff", pulseDuration: 1.2, spinBoost: 1 },
};

/* ------------------------------------------------------------------ */
/* Componente                                                         */
/* ------------------------------------------------------------------ */

function JarvisCoreBase() {
  const { state } = useJarvis();
  const cfg = STATE_CONFIG[state];

  const svgRef = useRef<SVGSVGElement>(null);
  const innerRingRef = useRef<SVGCircleElement>(null);
  const plasmaRef = useRef<SVGCircleElement>(null);
  const dataRingRef = useRef<SVGGElement>(null);
  const brokenRingRef = useRef<SVGGElement>(null);
  const glowRef = useRef<SVGFEGaussianBlurElement>(null);

  /* --- GSAP: pulso del círculo interno + glow dinámico ------------ */
  useEffect(() => {
    const ctx = gsap.context(() => {
      // Pulso de escala suave sobre el círculo de estado (transform-origin centro)
      gsap.to([innerRingRef.current, plasmaRef.current], {
        scale: 1.05,
        transformOrigin: "300px 300px",
        duration: cfg.pulseDuration / 2,
        yoyo: true,
        repeat: -1,
        ease: "sine.inOut",
      });

      // Transición de color hacia el del estado actual
      gsap.to(innerRingRef.current, {
        attr: { stroke: cfg.color },
        duration: 0.4,
        ease: "power2.out",
      });
      gsap.to(plasmaRef.current, {
        attr: { fill: `url(#plasma-${state})` },
        duration: 0.4,
      });

      // Glow dinámico: se intensifica con actividad (thinking/speaking/listening)
      const active = state !== "idle";
      gsap.to(glowRef.current!, {
        attr: { stdDeviation: active ? 7 : 4 },
        duration: 0.6,
        ease: "power2.out",
      });

      // Anillo de datos: 60s/vuelta en idle; más rápido si spinBoost > 0
      if (dataRingRef.current) {
        gsap.killTweensOf(dataRingRef.current);
        const dur = cfg.spinBoost > 0 ? Math.max(2, 12 / cfg.spinBoost) : 60;
        gsap.to(dataRingRef.current, {
          rotation: 360,
          transformOrigin: "300px 300px",
          duration: dur,
          repeat: -1,
          ease: "none",
        });
      }
      // Anillo discontinuo: 45s antihorario
      if (brokenRingRef.current) {
        gsap.to(brokenRingRef.current, {
          rotation: -360,
          transformOrigin: "300px 300px",
          duration: 45,
          repeat: -1,
          ease: "none",
        });
      }
    }, svgRef);
    return () => ctx.revert();
  }, [state, cfg]);

  return (
    <div className="relative flex items-center justify-center">
      {/* ---------- Ondas expansivas (Framer Motion) mientras habla ---------- */}
      <AnimatePresence>
        {state === "speaking"
          ? [0, 1, 2].map((i) => (
              <motion.span
                key={`wave-${i}`}
                className="pointer-events-none absolute rounded-full border border-jarvis/60"
                style={{ width: 200, height: 200 }}
                initial={{ scale: 0.6, opacity: 0.8 }}
                animate={{ scale: 3.2, opacity: 0 }}
                exit={{ opacity: 0 }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                  delay: i * 0.66,
                  ease: "easeOut",
                }}
              />
            ))
          : null}
      </AnimatePresence>

      {/* ---------- Escalado responsive sin romper aspect ratio ---------- */}
      <svg
        ref={svgRef}
        viewBox="0 0 600 600"
        className="h-[min(90vw,600px)] w-[min(90vw,600px)]"
        role="img"
        aria-label={`Núcleo JARVIS en estado ${state}`}
      >
        <defs>
          {/* Filtro de glow controlado dinámicamente por GSAP */}
          <filter id="core-glow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur ref={glowRef} stdDeviation="4" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          <filter id="soft-glow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="2.5" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Plasma radial por estado */}
          {(Object.keys(STATE_CONFIG) as JarvisState[]).map((s) => (
            <radialGradient key={s} id={`plasma-${s}`}>
              <stop offset="0%" stopColor={STATE_CONFIG[s].color} stopOpacity="0.9" />
              <stop offset="45%" stopColor={STATE_CONFIG[s].color} stopOpacity="0.25" />
              <stop offset="100%" stopColor={STATE_CONFIG[s].color} stopOpacity="0" />
            </radialGradient>
          ))}
        </defs>

        {/* ===== Círculo 5: Borde de contención (estático) ===== */}
        <circle
          cx={300} cy={300} r={240}
          fill="none" stroke="#ffffff" strokeOpacity={0.2} strokeWidth={1}
        />

        {/* Marcas de contención (ticks decorativos sobre el borde) */}
        <g stroke="#00f3ff" strokeOpacity={0.35} strokeWidth={1}>
          {Array.from({ length: 36 }).map((_, i) => {
            const a = (i * 10 * Math.PI) / 180;
            const r1 = 232, r2 = i % 3 === 0 ? 222 : 227;
            return (
              <line
                key={i}
                x1={300 + r1 * Math.cos(a)} y1={300 + r1 * Math.sin(a)}
                x2={300 + r2 * Math.cos(a)} y2={300 + r2 * Math.sin(a)}
              />
            );
          })}
        </g>

        {/* ===== Círculo 4: Radar exterior — pulso de opacidad 4s ===== */}
        <circle
          cx={300} cy={300} r={200}
          fill="none" stroke="#0044aa" strokeWidth={12}
          className="animate-radar-pulse"
        />

        {/* ===== Círculo 3: Discontinuo — antihorario 45s ===== */}
        <g ref={brokenRingRef}>
          <circle
            cx={300} cy={300} r={160}
            fill="none" stroke="#00f3ff" strokeOpacity={0.6}
            strokeWidth={3} strokeDasharray="5 15"
            filter="url(#soft-glow)"
          />
        </g>

        {/* ===== Círculo 2: Segmentos de datos — horario 60s ===== */}
        <g ref={dataRingRef}>
          <circle
            cx={300} cy={300} r={120}
            fill="none" stroke="#0066ff"
            strokeWidth={8} strokeDasharray="20 10" strokeLinecap="round"
            filter="url(#soft-glow)"
          />
        </g>

        {/* ===== Círculo 1: Estado — pulso + color dinámico + glow ===== */}
        <circle
          ref={plasmaRef}
          cx={300} cy={300} r={78}
          fill={`url(#plasma-${state})`}
        />
        <circle
          ref={innerRingRef}
          cx={300} cy={300} r={80}
          fill="none"
          stroke={cfg.color}
          strokeWidth={2}
          filter="url(#core-glow)"
        />

        {/* Punto central pulsante */}
        <circle cx={300} cy={300} r={6} fill={cfg.color} filter="url(#core-glow)">
          <animate
            attributeName="r" values="5;8;5"
            dur={`${cfg.pulseDuration}s`} repeatCount="indefinite"
          />
        </circle>

        {/* Texto de estado bajo el núcleo */}
        <text
          x={300} y={395}
          textAnchor="middle"
          fill={cfg.color}
          fontSize={14}
          letterSpacing={6}
          fontFamily="var(--font-share-tech-mono), monospace"
          opacity={0.85}
        >
          {state.toUpperCase()}
        </text>
      </svg>
    </div>
  );
}

/** Memoizado: sólo re-renderiza cuando cambia `state` del contexto. */
export const JarvisCore = memo(JarvisCoreBase);
export default JarvisCore;
