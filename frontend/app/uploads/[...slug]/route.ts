import { promises as fs } from "fs";
import path from "path";
import { NextRequest, NextResponse } from "next/server";

const DEFAULT_STORAGE_ROOT = "uploads";
const PUBLIC_UPLOAD_DIRS = new Set(["profile", "logos"]);

function normalizeStorageRoot(root: string): string {
  let normalized = root.trim();
  if (normalized.startsWith("/")) normalized = normalized.slice(1);
  if (normalized.startsWith("public/")) normalized = normalized.slice("public/".length);
  return normalized || DEFAULT_STORAGE_ROOT;
}

function resolveStorageRoot(): string {
  const root = normalizeStorageRoot(
    process.env.LOCAL_STORAGE_PATH || DEFAULT_STORAGE_ROOT
  );
  return path.resolve(process.cwd(), "public", root);
}

function contentTypeFor(filePath: string): string {
  const ext = path.extname(filePath).toLowerCase();
  switch (ext) {
    case ".jpg":
    case ".jpeg":
      return "image/jpeg";
    case ".png":
      return "image/png";
    case ".webp":
      return "image/webp";
    case ".gif":
      return "image/gif";
    case ".svg":
      return "image/svg+xml";
    default:
      return "application/octet-stream";
  }
}

export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ slug: string[] }> }
) {
  const { slug } = await context.params;
  if (!Array.isArray(slug) || slug.length < 2) {
    return new NextResponse("Not Found", { status: 404 });
  }

  const [topLevel] = slug;
  if (!PUBLIC_UPLOAD_DIRS.has(topLevel)) {
    return new NextResponse("Not Found", { status: 404 });
  }

  const storageRoot = resolveStorageRoot();
  const filePath = path.resolve(storageRoot, ...slug);

  // Prevent path traversal
  if (!filePath.startsWith(`${storageRoot}${path.sep}`)) {
    return new NextResponse("Not Found", { status: 404 });
  }

  try {
    const file = await fs.readFile(filePath);
    return new NextResponse(file, {
      status: 200,
      headers: {
        "Content-Type": contentTypeFor(filePath),
        // Filenames are stable; callers append ?v=timestamp when replacing files.
        "Cache-Control": "public, max-age=31536000, immutable",
      },
    });
  } catch {
    return new NextResponse("Not Found", { status: 404 });
  }
}
