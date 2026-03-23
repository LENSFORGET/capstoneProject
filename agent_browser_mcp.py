"""
Agent Browser MCP Server
Exposes agent-browser tools to NAT workflows via MCP stdio protocol.
Handles Windows vs Linux agent-browser command detection automatically.
"""
import sys
import platform
import shutil
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("agent-browser")


def _agent_browser_cmd() -> list[str]:
    """Detect the correct agent-browser CLI command for the current platform."""
    if platform.system() == "Windows":
        # On Windows, try npx agent-browser or the local install
        if shutil.which("agent-browser"):
            return ["agent-browser"]
        return ["npx", "-y", "agent-browser"]
    else:
        # On Linux/Mac (Docker container)
        if shutil.which("agent-browser"):
            return ["agent-browser"]
        # Try npx
        if shutil.which("npx"):
            return ["npx", "-y", "agent-browser"]
        return ["agent-browser"]


@mcp.tool()
def get_agent_browser_command() -> str:
    """Returns the detected agent-browser command for the current platform."""
    cmd = _agent_browser_cmd()
    return " ".join(cmd)


if __name__ == "__main__":
    mcp.run(transport="stdio")
