import { NextRequest, NextResponse } from "next/server";
import { getBackendBaseUrl } from "@/lib/backend-url";
import {
  createInternalAuthHeaders,
} from "@/lib/internal-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Enable Banking OAuth callback handler.
 *
 * After the user authorizes at their bank, they're redirected here with
 * ?code=... or ?error=...
 *
 * On success: exchanges code via backend, then redirects to settings.
 * On error: redirects to connect-bank page with error message.
 */
export async function GET(req: NextRequest) {
  const { searchParams } = req.nextUrl;
  const code = searchParams.get("code");
  const state = searchParams.get("state");
  const error = searchParams.get("error");

  const baseUrl = req.nextUrl.origin;

  // Handle error from bank
  if (error) {
    const errorDesc = searchParams.get("error_description") || error;
    return NextResponse.redirect(
      `${baseUrl}/settings/connect-bank?error=${encodeURIComponent(errorDesc)}`
    );
  }

  if (!code) {
    return NextResponse.redirect(
      `${baseUrl}/settings/connect-bank?error=${encodeURIComponent("No authorization code received")}`
    );
  }

  // Get user session to authenticate the backend call
  let userId: string;
  try {
    const { auth } = await import("@/lib/auth");
    const session = await auth.api.getSession({ headers: req.headers });
    if (!session?.user?.id) {
      return NextResponse.redirect(
        `${baseUrl}/login?redirect=${encodeURIComponent("/settings/connect-bank")}`
      );
    }
    userId = session.user.id;
  } catch {
    return NextResponse.redirect(
      `${baseUrl}/login?redirect=${encodeURIComponent("/settings/connect-bank")}`
    );
  }

  // Exchange code at backend
  try {
    const backendBase = getBackendBaseUrl().replace(/\/+$/, "");
    const upstreamUrl = `${backendBase}/api/enable-banking/session`;

    const signatureHeaders = createInternalAuthHeaders({
      method: "POST",
      pathWithQuery: "/api/enable-banking/session",
      userId,
    });

    const resp = await fetch(upstreamUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...signatureHeaders,
      },
      body: JSON.stringify({ code, state }),
    });

    if (!resp.ok) {
      const errorData = await resp.json().catch(() => ({ detail: "Unknown error" }));
      return NextResponse.redirect(
        `${baseUrl}/settings/connect-bank?error=${encodeURIComponent(errorData.detail || "Failed to connect bank")}`
      );
    }

    return NextResponse.redirect(
      `${baseUrl}/settings?tab=bank-connections&connected=true`
    );
  } catch (e) {
    return NextResponse.redirect(
      `${baseUrl}/settings/connect-bank?error=${encodeURIComponent("Failed to connect bank. Please try again.")}`
    );
  }
}
