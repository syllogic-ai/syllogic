import { promises as fs } from "fs";
import path from "path";
import type { StorageProvider, StorageFile, UploadOptions } from "./types";

const STORAGE_ROOT = process.env.LOCAL_STORAGE_PATH || "uploads";

export class LocalStorageProvider implements StorageProvider {
  private storageRoot: string;
  private baseUrl: string;

  constructor() {
    this.storageRoot = path.resolve(process.cwd(), "public", STORAGE_ROOT);
    this.baseUrl = `/${STORAGE_ROOT}`;
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
    return `${this.baseUrl}/${filePath}`;
  }
}
