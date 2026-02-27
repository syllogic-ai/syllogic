import type { NextRequest } from "next/server";
import { getBackendBaseUrl } from "@/lib/backend-url";
import {
  createInternalAuthHeaders,
  INTERNAL_AUTH_SIGNATURE_HEADER,
  INTERNAL_AUTH_TIMESTAMP_HEADER,
  INTERNAL_AUTH_USER_HEADER,
} from "@/lib/internal-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const UNPROTECTED_API_PATHS = new Set(["/api/health"]);

type ProxySession = {
  user?: {
    id?: string;
  } | null;
} | null;

function buildUpstreamUrl(req: NextRequest, pathSegments: string[]): URL {
  const backendBase = getBackendBaseUrl().replace(/\/+$/, "");
  const upstream = new URL(`${backendBase}/api/${pathSegments.join("/")}`);
  upstream.search = req.nextUrl.search;
  return upstream;
}

function cloneRequestHeaders(req: NextRequest): Headers {
  const headers = new Headers(req.headers);
  // Let fetch set these appropriately for the upstream request.
  headers.delete("host");
  headers.delete("connection");
  headers.delete("content-length");
  headers.delete(INTERNAL_AUTH_USER_HEADER);
  headers.delete(INTERNAL_AUTH_TIMESTAMP_HEADER);
  headers.delete(INTERNAL_AUTH_SIGNATURE_HEADER);
  return headers;
}

async function proxy(req: NextRequest, pathSegments: string[]) {
  const upstreamUrl = buildUpstreamUrl(req, pathSegments);
  const method = req.method.toUpperCase();
  const isProtectedPath = !UNPROTECTED_API_PATHS.has(upstreamUrl.pathname);

  let session: ProxySession = null;
  if (isProtectedPath) {
    try {
      const { auth } = await import("@/lib/auth");
      session = await auth.api.getSession({ headers: req.headers });
    } catch (error) {
      return Response.json(
        {
          detail:
            error instanceof Error
              ? error.message
              : "Authentication subsystem is not available",
        },
        { status: 500 }
      );
    }
  }

  if (isProtectedPath && !session?.user?.id) {
    return Response.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const requestHeaders = cloneRequestHeaders(req);
  if (isProtectedPath && session?.user?.id) {
    try {
      const signatureHeaders = createInternalAuthHeaders({
        method,
        pathWithQuery: `${upstreamUrl.pathname}${upstreamUrl.search}`,
        userId: session.user.id,
      });
      Object.entries(signatureHeaders).forEach(([key, value]) => {
        requestHeaders.set(key, value);
      });
    } catch (error) {
      return Response.json(
        {
          detail:
            error instanceof Error
              ? error.message
              : "Failed to sign internal request",
        },
        { status: 500 }
      );
    }
  }

  const init: RequestInit = {
    method,
    headers: requestHeaders,
    cache: "no-store",
  };

  if (method !== "GET" && method !== "HEAD") {
    const body = await req.arrayBuffer();
    init.body = body.byteLength ? body : undefined;
  }

  const upstreamRes = await fetch(upstreamUrl, init);

  // Pass through response status + headers. We remove hop-by-hop headers and let
  // the platform handle transfer encoding.
  const resHeaders = new Headers(upstreamRes.headers);
  resHeaders.delete("connection");
  resHeaders.delete("content-length");
  resHeaders.delete("transfer-encoding");

  return new Response(upstreamRes.body, {
    status: upstreamRes.status,
    statusText: upstreamRes.statusText,
    headers: resHeaders,
  });
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxy(req, path);
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxy(req, path);
}

export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxy(req, path);
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxy(req, path);
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxy(req, path);
}

export async function OPTIONS(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxy(req, path);
}
