/**
 * Route handler de NextAuth.js (App Router).
 * Sólo exporta GET/POST; la configuración vive en @/lib/auth/auth-options
 * (los route handlers de Next 14 no permiten exports adicionales).
 */
import { handler } from "@/lib/auth/auth-options";

export { handler as GET, handler as POST };
