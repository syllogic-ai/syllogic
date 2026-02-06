import type { NextRequest } from "next/server";
import { getBackendBaseUrl } from "@/lib/backend-url";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

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
  return headers;
}

async function proxy(req: NextRequest, pathSegments: string[]) {
  const upstreamUrl = buildUpstreamUrl(req, pathSegments);
  const method = req.method.toUpperCase();

  const init: RequestInit = {
    method,
    headers: cloneRequestHeaders(req),
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
