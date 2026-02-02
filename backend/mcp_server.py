"""
Entry point for the Personal Finance MCP Server.

Usage:
    stdio mode (for Claude Desktop):
        python mcp_server.py

    HTTP mode (for web deployment):
        uvicorn mcp_server:app --port 8001

    Using FastMCP CLI:
        fastmcp run mcp_server.py
"""
from app.mcp.server import mcp

# HTTP app for uvicorn deployment
app = mcp.http_app()

if __name__ == "__main__":
    # Run in stdio mode for Claude Desktop
    mcp.run()
