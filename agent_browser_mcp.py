"""
agent_browser_mcp.py
--------------------
浏览器自动化 FastMCP 服务，封装 agent-browser CLI。
供 NAT react_agent（workflow_scraper.yaml 等）通过 MCP 协议调用。

会话持久化：
  所有命令均使用 --session-name xhs，确保 cookies 和 localStorage
  在 agent-browser 守护进程重启后自动加载。
  state_load / state_save 工具可将会话状态导入/导出为 JSON 文件，
  便于 Docker 卷共享（xhs-login 容器登录后，nat-app 容器直接加载）。
"""

import platform
import subprocess
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Agent Browser")

CMD = "agent-browser.cmd" if platform.system() == "Windows" else "agent-browser"

# 所有命令共用的会话名称参数，确保 cookie/localStorage 自动持久化
_SESSION_ARGS = ["--session-name", "xhs"]


def _run(args: list[str]) -> str:
    """执行 agent-browser 命令，返回合并后的 stdout+stderr 字符串。"""
    try:
        result = subprocess.run(
            [CMD, *_SESSION_ARGS, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        return result.stdout + result.stderr
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def navigate(url: str) -> str:
    """Navigate to a URL in the browser. Use this first."""
    return _run(["open", url])


@mcp.tool()
def get_text(selector: str) -> str:
    """Get text content of an element by selector (e.g., @e1 or #id)."""
    try:
        result = subprocess.run(
            [CMD, *_SESSION_ARGS, "get", "text", selector],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def click(selector: str) -> str:
    """Click an element by selector (e.g., @e1 or #id)."""
    return _run(["click", selector])


@mcp.tool()
def type_text(selector: str, text: str) -> str:
    """Type text into an element (e.g., @e1 or #id)."""
    return _run(["type", selector, text])


@mcp.tool()
def press_key(key: str) -> str:
    """Press a key (e.g., Enter, Tab)."""
    return _run(["press", key])


@mcp.tool()
def snapshot() -> str:
    """Get accessibility tree snapshot with refs (e.g., @e1). Use this to see the page content and find element refs."""
    return _run(["snapshot"])


@mcp.tool()
def state_load(path: str = "/app/data/xhs_state.json") -> str:
    """
    从指定文件加载浏览器会话状态（cookies、localStorage 等）。
    在爬虫开始前调用，可恢复小红书的已登录状态，无需重新登录。

    Args:
        path: state JSON 文件路径，默认 /app/data/xhs_state.json
              该文件由 xhs-login 容器（xhs_login_helper.py）生成并写入共享卷。

    Returns:
        执行结果字符串，成功时包含 "Loaded" 或类似提示。
    """
    import os
    if not os.path.exists(path):
        return f"[state_load] 文件不存在: {path}。请先运行 docker-compose --profile login up xhs-login 完成登录。"
    try:
        # 必须与 state_save / navigate 等使用同一会话名，否则加载的 cookie 不会生效
        result = subprocess.run(
            [CMD, *_SESSION_ARGS, "state", "load", path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        output = result.stdout + result.stderr
        return f"[state_load] {output.strip() or '会话状态已加载。'}"
    except Exception as e:
        return f"[state_load] Error: {e}"


@mcp.tool()
def state_save(path: str = "/app/data/xhs_state.json") -> str:
    """
    将当前浏览器会话状态（cookies、localStorage 等）保存到文件。
    可用于备份当前登录态，或在会话刷新后手动更新 state 文件。

    Args:
        path: 保存路径，默认 /app/data/xhs_state.json

    Returns:
        执行结果字符串，成功时包含文件路径信息。
    """
    import os
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    try:
        result = subprocess.run(
            [CMD, *_SESSION_ARGS, "state", "save", path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        output = result.stdout + result.stderr
        exists = os.path.exists(path)
        return f"[state_save] {output.strip() or '完成。'} 文件存在: {exists}"
    except Exception as e:
        return f"[state_save] Error: {e}"


if __name__ == "__main__":
    mcp.run()
