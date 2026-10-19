import type { Metadata } from "next";
import { NextAuthSessionProvider } from "@/lib/auth/session-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "J.A.R.V.I.S. — Just A Rather Very Intelligent System",
  description:
    "Asistente de IA conversacional con HUD holográfico, memoria vectorial y control por voz.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es" className="dark">
      <body className="min-h-screen bg-void text-jarvis-light antialiased">
        <NextAuthSessionProvider>{children}</NextAuthSessionProvider>
      </body>
    </html>
  );
}
