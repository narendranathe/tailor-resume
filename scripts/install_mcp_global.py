"""
install_mcp_global.py
Register the tailor-resume MCP server in ~/.claude/.mcp.json.

Idempotent: safe to run multiple times. Preserves any existing servers
already in the config. Updates the tailor-resume entry if it exists.

Usage:
    python scripts/install_mcp_global.py
    make mcp-install-global
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SERVER_NAME = "tailor-resume"
SERVER_SCRIPT = (
    Path(__file__).parent.parent
    / ".claude/skills/tailor-resume/scripts/mcp_server.py"
).resolve()

GLOBAL_CONFIG = Path.home() / ".claude" / ".mcp.json"


def main() -> None:
    # Load existing config or start fresh
    config: dict = {"mcpServers": {}}
    if GLOBAL_CONFIG.exists():
        try:
            config = json.loads(GLOBAL_CONFIG.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"[WARNING] {GLOBAL_CONFIG} is not valid JSON — overwriting.")

    if "mcpServers" not in config:
        config["mcpServers"] = {}

    entry = {
        "command": sys.executable,
        "args": [str(SERVER_SCRIPT)],
        "env": {},
    }

    action = "Updated" if SERVER_NAME in config["mcpServers"] else "Registered"
    config["mcpServers"][SERVER_NAME] = entry

    GLOBAL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    GLOBAL_CONFIG.write_text(json.dumps(config, indent=2), encoding="utf-8")

    print(f"[OK] {action} '{SERVER_NAME}' in {GLOBAL_CONFIG}")
    print(f"     Server: {SERVER_SCRIPT}")
    print("     Restart Claude Code to pick up the change.")


if __name__ == "__main__":
    main()
