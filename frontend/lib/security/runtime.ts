export function isProductionEnvironment(): boolean {
  const productionMarkers = new Set(["production", "prod", "1", "true", "yes"]);
  const candidates = [
    process.env.NODE_ENV,
    process.env.ENVIRONMENT,
    process.env.APP_ENV,
    process.env.RAILWAY_ENVIRONMENT,
    process.env.RAILWAY_ENVIRONMENT_NAME,
  ];

  return candidates.some((value) => {
    const normalized = value?.trim().toLowerCase();
    return normalized ? productionMarkers.has(normalized) : false;
  });
}

export function databaseUrlRequiresTls(connectionString: string): boolean {
  return (
    /sslmode=(require|verify-ca|verify-full)/i.test(connectionString) ||
    /ssl=true/i.test(connectionString)
  );
}

export function shouldEnforceDatabaseTls(connectionString: string): boolean {
  const localHosts = new Set(["localhost", "127.0.0.1", "postgres", "db"]);
  try {
    const parsed = new URL(connectionString);
    return !localHosts.has(parsed.hostname.toLowerCase());
  } catch {
    return true;
  }
}

export function assertProductionDatabaseTls(connectionString: string, context: string): void {
  if (
    isProductionEnvironment() &&
    shouldEnforceDatabaseTls(connectionString) &&
    !databaseUrlRequiresTls(connectionString)
  ) {
    throw new Error(
      `[${context}] Production DATABASE_URL must enforce TLS. Use '?sslmode=require', '?sslmode=verify-ca', '?sslmode=verify-full', or '?ssl=true'.`
    );
  }
}
