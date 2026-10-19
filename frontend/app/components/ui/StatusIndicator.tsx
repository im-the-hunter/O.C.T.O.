import { cn } from "@/lib/utils/cn";

/**
 * StatusIndicator — Punto LED con glow, opcionalmente parpadeante.
 */
export default function StatusIndicator({
  color = "#00ff9d",
  pulse = true,
  className,
}: {
  color?: string;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={cn("inline-block h-2 w-2 rounded-full", className)}
      style={{
        backgroundColor: color,
        boxShadow: `0 0 6px ${color}, 0 0 14px ${color}66`,
        animation: pulse ? "jarvis-blink 1.6s ease-in-out infinite" : undefined,
      }}
    />
  );
}
