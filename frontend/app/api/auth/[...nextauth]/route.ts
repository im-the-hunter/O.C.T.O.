import NextAuth from "next-auth";
import GitHubProvider from "next-auth/providers/github";

/**
 * Configuración de NextAuth.js (App Router).
 * Provider principal: GitHub (coherente con la integración del backend).
 */
export const authOptions = {
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
    strategy: "jwt" as const,
  },
};

const handler = NextAuth(authOptions);

export { handler as GET, handler as POST };
