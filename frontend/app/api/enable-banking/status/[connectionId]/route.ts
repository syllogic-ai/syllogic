import { NextRequest, NextResponse } from "next/server";
import { getBackendBaseUrl } from "@/lib/backend-url";
import { createInternalAuthHeaders } from "@/lib/internal-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ connectionId: string }> }
) {
  const { connectionId } = await params;

  let userId: string;
  try {
    const { auth } = await import("@/lib/auth");
    const session = await auth.api.getSession({ headers: req.headers });
    if (!session?.user?.id) {
      return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
    }
    userId = session.user.id;
  } catch {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  try {
    const backendBase = getBackendBaseUrl().replace(/\/+$/, "");
    const pathWithQuery = `/api/enable-banking/status/${connectionId}`;
    const url = `${backendBase}${pathWithQuery}`;

    const signatureHeaders = createInternalAuthHeaders({
      method: "GET",
      pathWithQuery,
      userId,
    });

    const resp = await fetch(url, {
      method: "GET",
      headers: signatureHeaders,
    });

    if (!resp.ok) {
      const data = await resp.json().catch(() => ({ detail: "Status check failed" }));
      return NextResponse.json(data, { status: resp.status });
    }

    const data = await resp.json();
    return NextResponse.json(data);
  } catch (e) {
    return NextResponse.json(
      { detail: "Failed to check connection status" },
      { status: 500 }
    );
  }
}
