import NextAuth, { type NextAuthOptions } from "next-auth";
import GitHubProvider from "next-auth/providers/github";

/**
 * Configuración de NextAuth.js (Next 14 + next-auth v4).
 * Provider principal: GitHub (coherente con la integración del backend).
 * Se mantiene fuera de app/api para que route.ts sólo exporte GET/POST.
 */
export const authOptions: NextAuthOptions = {
  providers: [
    GitHubProvider({
      clientId: process.env.GITHUB_CLIENT_ID ?? "",
      clientSecret: process.env.GITHUB_CLIENT_SECRET ?? "",
    }),
  ],
  secret: process.env.NEXTAUTH_SECRET,
  pages: {
    signIn: "/auth/signin",
  },
  session: {
    strategy: "jwt",
  },
};

export const handler = NextAuth(authOptions);
