"use client";

import { SessionProvider } from "next-auth/react";

/**
 * Wrapper de sesión de NextAuth para el App Router.
 */
export function NextAuthSessionProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  return <SessionProvider>{children}</SessionProvider>;
}
