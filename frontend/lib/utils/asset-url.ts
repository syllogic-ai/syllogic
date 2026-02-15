function getVersionToken(
  updatedAt?: Date | string | number | null
): string | null {
  if (updatedAt === null || updatedAt === undefined) {
    return null;
  }

  if (typeof updatedAt === "number") {
    if (Number.isFinite(updatedAt)) {
      return String(Math.trunc(updatedAt));
    }
    return null;
  }

  const timestamp =
    updatedAt instanceof Date
      ? updatedAt.getTime()
      : new Date(updatedAt).getTime();

  if (Number.isNaN(timestamp)) {
    return null;
  }

  return String(timestamp);
}

export function withAssetVersion(
  url: string | null | undefined,
  updatedAt?: Date | string | number | null
): string | null {
  if (!url) {
    return null;
  }

  const versionToken = getVersionToken(updatedAt);
  if (!versionToken) {
    return url;
  }

  if (!url.startsWith("/")) {
    return url;
  }

  try {
    const parsed = new URL(url, "http://localhost");
    parsed.searchParams.set("v", versionToken);
    return `${parsed.pathname}${parsed.search}`;
  } catch {
    return url;
  }
}
