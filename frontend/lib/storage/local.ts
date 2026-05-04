import { promises as fs, existsSync } from "fs";
import path from "path";
import { resolveLocalStorageRoot } from "./local-paths";
import type { StorageProvider, StorageFile, UploadOptions } from "./types";

export class LocalStorageProvider implements StorageProvider {
  private storageRoot: string;
  private baseUrl: string;

  constructor() {
    this.storageRoot = resolveLocalStorageRoot();
    this.baseUrl = "/uploads";
    // Best-effort: ensure root exists so first uploads don't fail before mkdir.
    if (!existsSync(this.storageRoot)) {
      fs.mkdir(this.storageRoot, { recursive: true }).catch(() => {});
    }
  }

  private getFullPath(filePath: string): string {
    return path.join(this.storageRoot, filePath);
  }

  async upload(
    filePath: string,
    data: Buffer | Blob,
    options?: UploadOptions
  ): Promise<StorageFile> {
    const fullPath = this.getFullPath(filePath);
    const directory = path.dirname(fullPath);

    // Ensure directory exists
    await fs.mkdir(directory, { recursive: true });

    // Convert Blob to Buffer if needed
    const buffer = data instanceof Blob ? Buffer.from(await data.arrayBuffer()) : data;

    // Write the file
    await fs.writeFile(fullPath, buffer);

    const stats = await fs.stat(fullPath);

    return {
      path: filePath,
      url: this.getUrl(filePath),
      size: stats.size,
      contentType: options?.contentType,
      createdAt: stats.birthtime,
    };
  }

  async download(filePath: string): Promise<Buffer> {
    const fullPath = this.getFullPath(filePath);
    return fs.readFile(fullPath);
  }

  async delete(filePath: string): Promise<void> {
    const fullPath = this.getFullPath(filePath);
    try {
      await fs.unlink(fullPath);
    } catch (error) {
      // Ignore if file doesn't exist
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") {
        throw error;
      }
    }
  }

  async exists(filePath: string): Promise<boolean> {
    const fullPath = this.getFullPath(filePath);
    try {
      await fs.access(fullPath);
      return true;
    } catch {
      return false;
    }
  }

  async getMetadata(filePath: string): Promise<StorageFile | null> {
    const fullPath = this.getFullPath(filePath);
    try {
      const stats = await fs.stat(fullPath);
      return {
        path: filePath,
        url: this.getUrl(filePath),
        size: stats.size,
        createdAt: stats.birthtime,
      };
    } catch {
      return null;
    }
  }

  getUrl(filePath: string): string {
    return `${this.baseUrl}/${filePath.replace(/^\/+/, "")}`;
  }
}
