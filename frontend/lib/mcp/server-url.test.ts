import { describe, expect, it } from "vitest";

import { resolveMcpServerUrlForSnippet } from "./server-url";

describe("resolveMcpServerUrlForSnippet", () => {
  it("uses explicit MCP_SERVER_URL when provided", () => {
    const result = resolveMcpServerUrlForSnippet({
      mcpServerUrl: "https://custom.example.com/mcp",
      betterAuthUrl: "https://app.syllogic.ai",
    });

    expect(result).toBe("https://custom.example.com/mcp");
  });

  it("normalizes explicit MCP_SERVER_URL to /mcp path", () => {
    const result = resolveMcpServerUrlForSnippet({
      mcpServerUrl: "https://custom.example.com",
    });

    expect(result).toBe("https://custom.example.com/mcp");
  });

  it("derives local MCP URL from localhost BETTER_AUTH_URL", () => {
    const result = resolveMcpServerUrlForSnippet({
      betterAuthUrl: "http://localhost:8080",
    });

    expect(result).toBe("http://localhost:8001/mcp");
  });

  it("derives mcp subdomain from app subdomain", () => {
    const result = resolveMcpServerUrlForSnippet({
      betterAuthUrl: "https://app.syllogic.ai",
    });

    expect(result).toBe("https://mcp.syllogic.ai/mcp");
  });

  it("falls back to app URL when BETTER_AUTH_URL is not set", () => {
    const result = resolveMcpServerUrlForSnippet({
      appUrl: "https://app.example.com",
    });

    expect(result).toBe("https://mcp.example.com/mcp");
  });

  it("uses hosted default when no URLs are available", () => {
    const result = resolveMcpServerUrlForSnippet();

    expect(result).toBe("https://mcp.syllogic.ai/mcp");
  });
});
