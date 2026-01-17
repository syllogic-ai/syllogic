export interface UploadOptions {
  contentType?: string;
  metadata?: Record<string, string>;
}

export interface StorageFile {
  path: string;
  url: string;
  size: number;
  contentType?: string;
  createdAt: Date;
}

export interface StorageProvider {
  /**
   * Upload a file to storage
   * @param path - The storage path (e.g., "uploads/profile/user-123.jpg")
   * @param data - File data as Buffer or Blob
   * @param options - Upload options
   * @returns The stored file info
   */
  upload(path: string, data: Buffer | Blob, options?: UploadOptions): Promise<StorageFile>;

  /**
   * Download a file from storage
   * @param path - The storage path
   * @returns File data as Buffer
   */
  download(path: string): Promise<Buffer>;

  /**
   * Delete a file from storage
   * @param path - The storage path
   */
  delete(path: string): Promise<void>;

  /**
   * Check if a file exists
   * @param path - The storage path
   */
  exists(path: string): Promise<boolean>;

  /**
   * Get file metadata
   * @param path - The storage path
   */
  getMetadata(path: string): Promise<StorageFile | null>;

  /**
   * Get the public URL for a file
   * @param path - The storage path
   */
  getUrl(path: string): string;
}

export type StorageProviderType = "local" | "r2";
