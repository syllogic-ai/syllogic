import { LocalStorageProvider } from "./local";
import type { StorageProvider, StorageProviderType } from "./types";

export * from "./types";
export { LocalStorageProvider } from "./local";

let storageInstance: StorageProvider | null = null;

export function getStorageProvider(type?: StorageProviderType): StorageProvider {
  if (storageInstance) {
    return storageInstance;
  }

  const providerType = type || (process.env.STORAGE_PROVIDER as StorageProviderType) || "local";

  switch (providerType) {
    case "local":
      storageInstance = new LocalStorageProvider();
      break;
    case "r2":
      // R2 support can be added later
      throw new Error("R2 storage provider not implemented yet");
    default:
      storageInstance = new LocalStorageProvider();
  }

  return storageInstance;
}

// Convenience function to get the default storage provider
export const storage = {
  get provider(): StorageProvider {
    return getStorageProvider();
  },
  upload: (...args: Parameters<StorageProvider["upload"]>) =>
    getStorageProvider().upload(...args),
  download: (...args: Parameters<StorageProvider["download"]>) =>
    getStorageProvider().download(...args),
  delete: (...args: Parameters<StorageProvider["delete"]>) =>
    getStorageProvider().delete(...args),
  exists: (...args: Parameters<StorageProvider["exists"]>) =>
    getStorageProvider().exists(...args),
  getMetadata: (...args: Parameters<StorageProvider["getMetadata"]>) =>
    getStorageProvider().getMetadata(...args),
  getUrl: (...args: Parameters<StorageProvider["getUrl"]>) =>
    getStorageProvider().getUrl(...args),
};
