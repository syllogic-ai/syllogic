import { oauthProviderAuthServerMetadata } from "@better-auth/oauth-provider";
import { auth } from "@/lib/auth";

// RFC 8414 requires the discovery URL to interpolate the issuer's path
// component: for issuer `https://app.syllogic.ai/api/auth`, the metadata
// lives at `/.well-known/oauth-authorization-server/api/auth`. Claude on
// iOS follows the spec strictly and only probes this path; Claude Desktop
// also accepts the path-less form at the site root. Expose both.
export const GET = oauthProviderAuthServerMetadata(auth);
