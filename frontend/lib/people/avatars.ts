import { storage } from "@/lib/storage";

const ALLOWED_MIME = new Set(["image/jpeg", "image/png", "image/webp", "image/gif"]);
const MAX_BYTES = 2 * 1024 * 1024; // 2 MB

export async function uploadPersonAvatar(personId: string, file: File): Promise<string> {
  if (!ALLOWED_MIME.has(file.type)) {
    throw new Error(`Unsupported avatar type: ${file.type}`);
  }
  if (file.size > MAX_BYTES) {
    throw new Error(`Avatar too large (max 2 MB)`);
  }
  const ext =
    file.type === "image/png"
      ? "png"
      : file.type === "image/webp"
        ? "webp"
        : file.type === "image/gif"
          ? "gif"
          : "jpg";
  const path = `people/${personId}.${ext}`;
  const buf = Buffer.from(await file.arrayBuffer());
  await storage.upload(path, buf, { contentType: file.type });
  return path;
}

export async function deletePersonAvatar(path: string): Promise<void> {
  if (!path) return;
  try {
    await storage.delete(path);
  } catch {
    // best-effort; ignore missing files
  }
}

export function avatarUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  return storage.getUrl(path);
}
