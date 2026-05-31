import { promises as fs } from "fs";
import path from "path";
import { NextRequest, NextResponse } from "next/server";
import { resolveLocalStorageRoot } from "@/lib/storage/local-paths";

// Subdirectories of the storage root that may be served publicly.
// CSV imports and other private files must NOT be added here.
const PUBLIC_UPLOAD_DIRS = new Set(["profile", "logos", "people"]);

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

  const storageRoot = resolveLocalStorageRoot();
  const filePath = path.resolve(storageRoot, ...slug);

  // Prevent path traversal
  if (
    filePath !== storageRoot &&
    !filePath.startsWith(`${storageRoot}${path.sep}`)
  ) {
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
