"use client";

/**
 * ScanLine — Línea horizontal semitransparente que recorre la pantalla
 * de abajo hacia arriba y viceversa cada ~5 segundos (Framer Motion).
 * Efecto "atención" del HUD: también parpadea suavemente.
 */
import { motion } from "framer-motion";

export default function ScanLine() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 z-40 overflow-hidden">
      <motion.div
        className="absolute left-0 h-[2px] w-full"
        style={{
          background:
            "linear-gradient(90deg, transparent, rgba(0,243,255,0.35) 20%, rgba(0,243,255,0.6) 50%, rgba(0,243,255,0.35) 80%, transparent)",
          boxShadow: "0 0 12px rgba(0,243,255,0.5), 0 0 32px rgba(0,243,255,0.25)",
        }}
        initial={{ y: "100vh" }}
        animate={{ y: ["100vh", "-2vh", "100vh"], opacity: [0.5, 0.9, 0.5] }}
        transition={{
          duration: 5,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />
      {/* Textura CRT sutil: líneas horizontales fijas */}
      <div
        className="absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage:
            "repeating-linear-gradient(0deg, #ffffff 0px, #ffffff 1px, transparent 1px, transparent 3px)",
        }}
      />
    </div>
  );
}
