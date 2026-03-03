const DEFAULT_MCP_SERVER_URL = "https://mcp.syllogic.ai/mcp";

type ClaudeDesktopServerConfig = {
  command: "npx";
  args: string[];
  env: {
    SYLLOGIC_AUTH_HEADER: string;
  };
};

export type ClaudeDesktopMcpConfig = {
  mcpServers: {
    syllogic: ClaudeDesktopServerConfig;
  };
};

function resolveMcpServerUrl(mcpUrl?: string): string {
  const trimmed = mcpUrl?.trim();
  if (!trimmed) {
    return DEFAULT_MCP_SERVER_URL;
  }
  return trimmed;
}

export function buildClaudeDesktopMcpConfig(
  apiKey: string,
  mcpUrl?: string
): ClaudeDesktopMcpConfig {
  const resolvedMcpUrl = resolveMcpServerUrl(mcpUrl);
  const args = [
    "-y",
    "mcp-remote@latest",
    resolvedMcpUrl,
    "--transport",
    "http-only",
    "--header",
    "Authorization:${SYLLOGIC_AUTH_HEADER}",
  ];

  if (resolvedMcpUrl.toLowerCase().startsWith("http://")) {
    args.push("--allow-http");
  }

  return {
    mcpServers: {
      syllogic: {
        command: "npx",
        args,
        env: {
          SYLLOGIC_AUTH_HEADER: `Bearer ${apiKey}`,
        },
      },
    },
  };
}

export function stringifyClaudeDesktopMcpConfig(
  apiKey: string,
  mcpUrl?: string
): string {
  return JSON.stringify(buildClaudeDesktopMcpConfig(apiKey, mcpUrl), null, 2);
}
