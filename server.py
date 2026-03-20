"""
server.py — HTTP/SSE entrypoint for tailor-resume MCP server.

Deploy: fly deploy
Local test: python server.py
Register in Claude Code: {"mcpServers": {"tailor-resume": {"url": "http://localhost:8080/mcp"}}}
"""
import os
import sys

# Add pipeline scripts to path
_scripts = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".claude", "skills", "tailor-resume", "scripts")
sys.path.insert(0, _scripts)

from mcp_server import mcp  # noqa: E402


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    print(f"[tailor-resume MCP] starting on http://0.0.0.0:{port}/mcp")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port, path="/mcp")


if __name__ == "__main__":
    main()
