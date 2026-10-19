"use client";

/**
 * JarvisCore — Núcleo SVG animado de J.A.R.V.I.S.
 *
 * 5 círculos concéntricos (viewBox 600x600, centro en 300,300):
 *  1. Estado      r=80   grosor 2    cian #00f3ff + glow, pulso suave de escala
 *  2. Datos       r=120  grosor 8    azul #0066ff, dash "20 10", rotación horaria lenta
 *  3. Discontinuo r=160  grosor 3    cian op 0.6, dash "5 15", rotación antihoraria
 *  4. Radar       r=200  grosor 12   azul oscuro #0044aa op 0.3, pulso de opacidad
 *  5. Contención  r=240  grosor 1    blanco op 0.2, estático
 *
 * Estados (prop `status`):
 *  - idle:      cian pulsante
 *  - listening: naranja (#ff6b00) pulsante rápido
 *  - thinking:  blanco con rotación rápida del anillo de datos
 *  - speaking:  cian con ondas expansivas (3 círculos que se expanden y desvanecen)
 *
 * Tailwind para estilos base + <style> con CSS personalizado para las
 * animaciones complejas de rotación y pulso (suaves y continuas).
 */
import type { FC } from "react";

export type JarvisStatus = "idle" | "listening" | "thinking" | "speaking";

interface JarvisCoreProps {
  status?: JarvisStatus;
  className?: string;
}

/* Paleta por estado ---------------------------------------------------- */
const STATUS_COLORS: Record<JarvisStatus, string> = {
  idle: "#00f3ff",
  listening: "#ff6b00",
  thinking: "#ffffff",
  speaking: "#00f3ff",
};

const JarvisCore: FC<JarvisCoreProps> = ({ status = "idle", className = "" }) => {
  const color = STATUS_COLORS[status];

  return (
    <div
      className={`relative flex h-full w-full items-center justify-center ${className}`}
      aria-label={`Núcleo JARVIS — estado: ${status}`}
    >
      {/* ---------------------------------------------------------------- */}
      {/* CSS personalizado para animaciones complejas                      */}
      {/* ---------------------------------------------------------------- */}
      {/* eslint-disable-next-line react/no-danger */}
      <style dangerouslySetInnerHTML={{ __html: `
        .jarvis-core-svg {
          width: min(90vmin, 640px);
          height: min(90vmin, 640px);
          overflow: visible;
        }

        /* --- Círculo 1: pulso de escala suave (transform-origin al centro) */
        @keyframes core-pulse-idle {
          0%, 100% { transform: scale(1); }
          50%      { transform: scale(1.05); }
        }
        @keyframes core-pulse-fast {
          0%, 100% { transform: scale(1); }
          50%      { transform: scale(1.08); }
        }
        .ring-inner {
          transform-origin: 300px 300px;
          animation: core-pulse-idle 2s ease-in-out infinite;
        }
        .status-listening .ring-inner {
          animation: core-pulse-fast 0.6s ease-in-out infinite;
        }
        .status-thinking .ring-inner {
          animation: core-pulse-fast 0.4s linear infinite;
        }

        /* --- Glow dinámico (filtro SVG aplicado vía clase de estado) */
        @keyframes glow-breathe {
          0%, 100% { opacity: 0.85; }
          50%      { opacity: 1; }
        }
        .glow-layer {
          animation: glow-breathe 2s ease-in-out infinite;
        }

        /* --- Círculo 2: rotación horaria lenta */
        @keyframes spin-cw {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        .ring-data {
          transform-origin: 300px 300px;
          animation: spin-cw 60s linear infinite;
        }
        .status-thinking .ring-data {
          animation: spin-cw 4s linear infinite;
        }

        /* --- Círculo 3: rotación antihoraria */
        @keyframes spin-ccw {
          from { transform: rotate(0deg); }
          to   { transform: rotate(-360deg); }
        }
        .ring-dashed {
          transform-origin: 300px 300px;
          animation: spin-ccw 45s linear infinite;
        }
        .status-thinking .ring-dashed {
          animation: spin-ccw 8s linear infinite;
        }

        /* --- Círculo 4: pulso de opacidad cada 4s */
        @keyframes radar-opacity {
          0%, 100% { opacity: 0.3; }
          50%      { opacity: 0.6; }
        }
        .ring-radar {
          animation: radar-opacity 4s ease-in-out infinite;
        }

        /* --- Ondas expansivas (solo cuando status === "speaking") */
        @keyframes ripple-expand {
          0%   { transform: scale(0.35); opacity: 0.9; }
          100% { transform: scale(1.45); opacity: 0; }
        }
        .ripple {
          transform-origin: 300px 300px;
          animation: ripple-expand 2.4s cubic-bezier(0.2, 0.6, 0.35, 1) infinite;
          opacity: 0;
        }
        .ripple-2 { animation-delay: 0.8s; }
        .ripple-3 { animation-delay: 1.6s; }

        /* Plasma interior del reactor */
        @keyframes plasma-spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        .plasma {
          transform-origin: 300px 300px;
          animation: plasma-spin 20s linear infinite;
        }
        .status-thinking .plasma {
          animation: plasma-spin 2s linear infinite;
        }
      ` }} />

      {/* ---------------------------------------------------------------- */}
      {/* SVG del núcleo                                                     */}
      {/* ---------------------------------------------------------------- */}
      <svg
        viewBox="0 0 600 600"
        className={`jarvis-core-svg status-${status}`}
        role="img"
      >
        <defs>
          {/* Filtro de glow intenso */}
          <filter id="core-glow" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="6" result="blur1" />
            <feGaussianBlur stdDeviation="14" result="blur2" />
            <feMerge>
              <feMergeNode in="blur2" />
              <feMergeNode in="blur1" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Glow sutil para el anillo de datos */}
          <filter id="soft-glow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="3" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Gradiente radial del plasma central */}
          <radialGradient id="plasma-gradient" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor={color} stopOpacity="0.9" />
            <stop offset="45%" stopColor={color} stopOpacity="0.25" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* ---- Plasma interior (glow dinámico que respira) ---- */}
        <g className="glow-layer">
          <circle cx="300" cy="300" r={status === "thinking" ? 70 : 60} fill="url(#plasma-gradient)" />
        </g>

        {/* ---- Ondas expansivas: solo en estado "speaking" ---- */}
        {status === "speaking" && (
          <g filter="url(#soft-glow)">
            <circle className="ripple ripple-1" cx="300" cy="300" r="80" fill="none" stroke="#00f3ff" strokeWidth="2" />
            <circle className="ripple ripple-2" cx="300" cy="300" r="80" fill="none" stroke="#00f3ff" strokeWidth="1.5" />
            <circle className="ripple ripple-3" cx="300" cy="300" r="80" fill="none" stroke="#00f3ff" strokeWidth="1" />
          </g>
        )}

        {/* ---- Círculo 5 (externo): borde de contención, estático ---- */}
        <circle cx="300" cy="300" r="240" fill="none" stroke="#ffffff" strokeOpacity="0.2" strokeWidth="1" />

        {/* ---- Círculo 4: radar exterior, pulso de opacidad 4s ---- */}
        <circle className="ring-radar" cx="300" cy="300" r="200" fill="none" stroke="#0044aa" strokeOpacity="0.3" strokeWidth="12" />

        {/* ---- Círculo 3: discontinuo, rotación antihoraria ---- */}
        <circle
          className="ring-dashed"
          cx="300"
          cy="300"
          r="160"
          fill="none"
          stroke="#00f3ff"
          strokeOpacity="0.6"
          strokeWidth="3"
          strokeDasharray="5 15"
          strokeLinecap="round"
        />

        {/* ---- Círculo 2: segmentos de datos, rotación horaria lenta ---- */}
        <circle
          className="ring-data"
          cx="300"
          cy="300"
          r="120"
          fill="none"
          stroke={status === "thinking" ? "#ffffff" : "#0066ff"}
          strokeWidth="8"
          strokeDasharray="20 10"
          strokeLinecap="butt"
          filter="url(#soft-glow)"
        />

        {/* ---- Marcas orbitales decorativas sobre el plasma ---- */}
        <g className="plasma" opacity="0.7">
          <circle cx="300" cy="248" r="3" fill={color} filter="url(#soft-glow)" />
          <circle cx="352" cy="300" r="2" fill={color} filter="url(#soft-glow)" />
          <circle cx="300" cy="352" r="2.5" fill={color} filter="url(#soft-glow)" />
          <circle cx="248" cy="300" r="1.5" fill={color} filter="url(#soft-glow)" />
        </g>

        {/* ---- Círculo 1 (interno): estado, pulso suave + glow intenso ---- */}
        <g className="ring-inner">
          <circle
            cx="300"
            cy="300"
            r="80"
            fill="none"
            stroke={color}
            strokeWidth="2"
            filter="url(#core-glow)"
            style={{ transition: "stroke 0.4s ease" }}
          />
          {/* Punto central del reactor */}
          <circle cx="300" cy="300" r="6" fill={color} filter="url(#core-glow)" style={{ transition: "fill 0.4s ease" }} />
        </g>
      </svg>
    </div>
  );
};

export default JarvisCore;
