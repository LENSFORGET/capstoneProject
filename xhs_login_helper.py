"""
xhs_login_helper.py
-------------------
小红书手动登录助手，运行在 xhs-login Docker 容器内。

功能：
  1. 通过 agent-browser（--headed 模式）打开小红书，配合 Xvfb 虚拟显示
  2. 用户通过 http://localhost:6080（noVNC）在浏览器中操作 Chromium 完成登录
  3. 登录完成后按 Enter，脚本自动保存会话至 /app/data/xhs_state.json
  4. 该 state 文件与 nat-app 容器共享同一 app_data 卷，爬虫启动时自动加载

运行方式：
  # 由 Dockerfile.login 的 CMD 自动调用，无需手动运行
  docker-compose --profile login up xhs-login --build

用户操作流程：
  1. 运行上述命令
  2. 打开 http://localhost:6080
  3. 在网页中看到 Chromium 浏览器，手动完成小红书登录（扫码或账号密码）
  4. 确认登录成功（看到首页内容）后，回到此终端按 Enter
  5. 会话自动保存，之后可运行爬虫：
     docker exec -it nat-app bash -c "nat run --config_file workflow_scraper.yaml --input '请现在开始执行采集任务。'"
"""

import os
import subprocess
import sys
import time

CMD = "agent-browser"
SESSION_ARGS = ["--session-name", "xhs"]
STATE_PATH = "/app/data/xhs_state.json"
XHS_URL = "https://www.xiaohongshu.com"

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║           小红书登录助手 - XHS Login Helper                   ║
╠══════════════════════════════════════════════════════════════╣
║  1. 请打开浏览器访问: http://localhost:6080                   ║
║  2. 在 noVNC 界面中可以看到 Chromium 浏览器                   ║
║  3. 在 Chromium 中完成小红书登录（扫码或账号密码）             ║
║  4. 确认登录成功后，回到此终端按 Enter 保存会话               ║
╚══════════════════════════════════════════════════════════════╝
"""


def run_cmd(args: list[str], check: bool = False) -> subprocess.CompletedProcess:
    """执行 agent-browser 命令，捕获输出。"""
    full_args = [CMD, *SESSION_ARGS, *args]
    print(f"[CMD] {' '.join(full_args)}")
    return subprocess.run(full_args, capture_output=True, text=True, check=check)


def check_agent_browser() -> bool:
    """确认 agent-browser 可用。"""
    try:
        result = subprocess.run([CMD, "--version"], capture_output=True, text=True)
        print(f"[INFO] agent-browser: {result.stdout.strip() or result.stderr.strip()}")
        return True
    except FileNotFoundError:
        print("[ERROR] agent-browser 未找到，请确认已安装。")
        return False


def open_xhs() -> bool:
    """打开小红书首页。"""
    print(f"\n[INFO] 正在打开 {XHS_URL}...")
    result = run_cmd(["--headed", "open", XHS_URL])
    if result.returncode != 0:
        print(f"[WARN] 打开页面时出现警告: {result.stderr.strip()}")
    else:
        print("[INFO] Chromium 已启动，请在 http://localhost:6080 查看。")
    return True


TRIGGER_FILE = "/app/data/xhs_login_trigger"


def wait_for_user_login() -> None:
    """
    等待用户在 noVNC 中完成登录操作。

    由于 docker-compose up 不会连接 stdin，改用文件触发方式：
    用户登录完成后，在另一个终端执行：
      docker exec xhs-login touch /app/data/xhs_login_trigger
    脚本检测到该文件后自动保存会话并继续。
    """
    # 清除残留触发文件
    if os.path.exists(TRIGGER_FILE):
        os.remove(TRIGGER_FILE)

    print(BANNER)
    print("=" * 64)
    print("  登录完成后，请在另一个终端执行以下命令触发保存：")
    print()
    print("    docker exec xhs-login touch /app/data/xhs_login_trigger")
    print()
    print("  脚本将自动检测并保存会话状态。")
    print("=" * 64)
    print()

    # 轮询触发文件，最长等待 10 分钟
    timeout = 600
    interval = 3
    elapsed = 0
    while elapsed < timeout:
        if os.path.exists(TRIGGER_FILE):
            os.remove(TRIGGER_FILE)
            print("[INFO] 检测到触发信号，开始保存会话...")
            return
        time.sleep(interval)
        elapsed += interval
        if elapsed % 30 == 0:
            remaining = timeout - elapsed
            print(f"[等待] 已等待 {elapsed}s，剩余 {remaining}s... 请在 noVNC 完成登录后执行 docker exec 命令。")

    print("[WARN] 等待超时（10分钟），尝试直接保存当前状态...")


def save_session_state() -> bool:
    """保存当前会话状态到文件。"""
    # 确保目录存在
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)

    print(f"\n[INFO] 正在保存会话状态至 {STATE_PATH}...")
    result = run_cmd(["state", "save", STATE_PATH])

    if result.returncode != 0:
        print(f"[ERROR] 保存会话失败: {result.stderr.strip()}")
        return False

    if os.path.exists(STATE_PATH):
        size = os.path.getsize(STATE_PATH)
        print(f"[OK] 会话已保存！文件大小: {size} bytes")
        return True
    else:
        print("[ERROR] state save 命令执行成功但文件未生成，请检查路径权限。")
        return False


def take_screenshot_for_verification() -> None:
    """截图以便验证登录状态（可选）。"""
    screenshot_path = "/app/data/xhs_login_verify.png"
    print(f"\n[INFO] 截图验证登录状态: {screenshot_path}")
    result = subprocess.run(
        [CMD, *SESSION_ARGS, "screenshot", screenshot_path],
        capture_output=True, text=True
    )
    if result.returncode == 0 and os.path.exists(screenshot_path):
        print(f"[OK] 截图已保存至 {screenshot_path}")
    else:
        print(f"[WARN] 截图失败: {result.stderr.strip()}")


def main() -> int:
    print("=" * 64)
    print("  小红书登录助手启动")
    print("=" * 64)

    # 1. 检查 agent-browser
    if not check_agent_browser():
        return 1

    # 2. 打开小红书
    if not open_xhs():
        return 1

    # 3. 等待用户完成登录
    wait_for_user_login()

    # 4. 截图验证（可选，不影响流程）
    take_screenshot_for_verification()

    # 5. 保存会话状态
    if not save_session_state():
        print("\n[ERROR] 会话保存失败，请重新运行此脚本。")
        return 1

    print("\n" + "=" * 64)
    print("  登录完成！")
    print("=" * 64)
    print(f"\n  会话文件: {STATE_PATH}")
    print("\n  现在可以运行爬虫（在另一个终端执行）：")
    print('  docker exec -it nat-app bash -c "nat run --config_file workflow_scraper.yaml --input \'请现在开始执行采集任务。\'"')
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
