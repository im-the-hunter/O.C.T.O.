import { cn } from "@/lib/utils/cn";

/**
 * HudPanel — Marco translúcido estilo consola de nave espacial.
 * Esquinas cortadas (clip-path) + borde cian tenue + blur.
 */
export default function HudPanel({
  children,
  className,
  title,
}: {
  children: React.ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <div
      className={cn(
        "relative border border-jarvis/20 bg-black/50 backdrop-blur-md",
        className
      )}
      style={{
        clipPath:
          "polygon(12px 0, 100% 0, 100% calc(100% - 12px), calc(100% - 12px) 100%, 0 100%, 0 12px)",
        boxShadow:
          "inset 0 0 24px rgba(0,243,255,0.06), 0 0 12px rgba(0,243,255,0.12)",
      }}
    >
      {title && (
        <div className="flex items-center gap-2 border-b border-jarvis/15 px-3 py-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-jarvis shadow-glow-cyan" />
          <span className="font-tech text-[10px] uppercase tracking-[0.3em] text-jarvis/80">
            {title}
          </span>
        </div>
      )}
      {children}
    </div>
  );
}
