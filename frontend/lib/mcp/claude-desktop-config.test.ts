import { describe, expect, it } from "vitest";

import {
  buildClaudeDesktopMcpConfig,
  stringifyClaudeDesktopMcpConfig,
} from "./claude-desktop-config";

describe("buildClaudeDesktopMcpConfig", () => {
  it("uses the hosted default MCP URL when no override is provided", () => {
    const config = buildClaudeDesktopMcpConfig("pf_test_key");
    const serverConfig = config.mcpServers.syllogic;

    expect(serverConfig.args).toContain("https://mcp.syllogic.ai/mcp");
  });

  it("uses the provided MCP URL override exactly", () => {
    const config = buildClaudeDesktopMcpConfig(
      "pf_test_key",
      "https://example.com/custom/mcp"
    );
    const serverConfig = config.mcpServers.syllogic;

    expect(serverConfig.args).toContain("https://example.com/custom/mcp");
    expect(serverConfig.args).not.toContain("https://mcp.syllogic.ai/mcp");
  });

  it("wires the auth header placeholder and bearer value correctly", () => {
    const config = buildClaudeDesktopMcpConfig("pf_secret");
    const serverConfig = config.mcpServers.syllogic;

    expect(serverConfig.args).toContain("--header");
    expect(serverConfig.args).toContain("Authorization:${SYLLOGIC_AUTH_HEADER}");
    expect(serverConfig.env.SYLLOGIC_AUTH_HEADER).toBe("Bearer pf_secret");
  });

  it("uses syllogic branding and excludes legacy naming in serialized output", () => {
    const serialized = stringifyClaudeDesktopMcpConfig("pf_test_key");

    expect(serialized).toContain('"syllogic"');
    expect(serialized).not.toContain("personal-finance");
    expect(serialized).not.toContain("PERSONAL_FINANCE_API_KEY");
  });

  it("appends --allow-http for http endpoints", () => {
    const config = buildClaudeDesktopMcpConfig(
      "pf_test_key",
      "http://localhost:8001/mcp"
    );
    const serverConfig = config.mcpServers.syllogic;

    expect(serverConfig.args).toContain("--allow-http");
  });
});
