import { DEFAULT_MCP_SERVER_URL } from "./claude-desktop-config";

type ResolveMcpServerUrlOptions = {
  mcpServerUrl?: string;
  betterAuthUrl?: string;
  appUrl?: string;
};

function parseUrl(value?: string): URL | null {
  const trimmed = value?.trim();
  if (!trimmed) return null;
  try {
    return new URL(trimmed);
  } catch {
    return null;
  }
}

function isIpAddress(hostname: string): boolean {
  if (hostname.includes(":")) return true; // IPv6
  return /^(\d{1,3}\.){3}\d{1,3}$/.test(hostname);
}

function isLocalHost(hostname: string): boolean {
  return (
    hostname === "localhost" ||
    hostname === "127.0.0.1" ||
    hostname === "::1"
  );
}

function ensureMcpPath(url: URL): URL {
  url.pathname = "/mcp";
  url.search = "";
  url.hash = "";
  return url;
}

function withMcpSubdomain(url: URL): URL {
  const next = new URL(url.toString());
  const hostname = next.hostname;

  if (isLocalHost(hostname) || isIpAddress(hostname)) {
    next.port = "8001";
    return ensureMcpPath(next);
  }

  const labels = hostname.split(".");
  if (labels[0] === "app" || labels[0] === "www") {
    labels[0] = "mcp";
  } else if (labels[0] !== "mcp") {
    labels.unshift("mcp");
  }

  next.hostname = labels.join(".");
  next.port = "";
  return ensureMcpPath(next);
}

export function resolveMcpServerUrlForSnippet(
  options: ResolveMcpServerUrlOptions = {}
): string {
  const explicit = parseUrl(options.mcpServerUrl);
  if (explicit) {
    return ensureMcpPath(explicit).toString();
  }

  const base = parseUrl(options.betterAuthUrl) ?? parseUrl(options.appUrl);
  if (!base) {
    return DEFAULT_MCP_SERVER_URL;
  }

  return withMcpSubdomain(base).toString();
}
