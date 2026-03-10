"""
xhs_login_helper.py
-------------------
小红书手动登录助手，支持 Docker（xhs-login 容器）和本地运行。

Docker 模式：
  1. agent-browser --headed 配合 Xvfb，用户通过 http://localhost:6080（noVNC）操作
  2. 登录后执行 docker exec xhs-login touch /app/data/xhs_login_trigger 触发保存
  3. 会话保存至 XHS_STATE_PATH（默认 /app/data/xhs_state.json）

本地模式：
  1. agent-browser --headed 直接打开 Chromium 窗口
  2. 用户完成登录后，在另一终端 touch 触发文件，或通过 stdin 按 Enter（若支持）
  3. 会话保存至 XHS_STATE_PATH（默认 ./data/xhs_state.json）

运行方式：
  Docker: docker-compose --profile login up xhs-login --build
  本地:   设置 XHS_STATE_PATH 后运行 python xhs_login_helper.py，或使用 scripts\\xhs_login_local.ps1
"""

import os
import platform
import subprocess
import sys
import time

# 优先使用项目本地安装（npm install agent-browser），避免全局 -g 的 EPERM 权限问题
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_LOCAL_AB = os.path.join(_PROJECT_ROOT, "node_modules", "agent-browser")
CMD_BASE = ["npx", "--yes", "agent-browser"] if os.path.isdir(_LOCAL_AB) else (["agent-browser.cmd"] if platform.system() == "Windows" else ["agent-browser"])
SESSION_ARGS = ["--session-name", "xhs"]
# 支持 XHS_STATE_PATH 环境变量，Docker 默认 /app/data，本地默认 ./data
_STATE_PATH = os.environ.get(
    "XHS_STATE_PATH",
    os.path.join(os.getcwd(), "data", "xhs_state.json")
    if not os.path.exists("/.dockerenv")
    else "/app/data/xhs_state.json",
)
TRIGGER_FILE = os.environ.get(
    "XHS_TRIGGER_FILE",
    os.path.join(os.path.dirname(_STATE_PATH), "xhs_login_trigger"),
)
XHS_URL = "https://www.xiaohongshu.com"

BANNER_DOCKER = """
╔══════════════════════════════════════════════════════════════╗
║           小红书登录助手 - XHS Login Helper (Docker)          ║
╠══════════════════════════════════════════════════════════════╣
║  1. 请打开浏览器访问: http://localhost:6080                   ║
║  2. 在 noVNC 界面中可以看到 Chromium 浏览器                   ║
║  3. 在 Chromium 中完成小红书登录（扫码或账号密码）             ║
║  4. 登录完成后，在另一终端执行 docker exec 命令触发保存       ║
╚══════════════════════════════════════════════════════════════╝
"""

BANNER_LOCAL = """
╔══════════════════════════════════════════════════════════════╗
║           小红书登录助手 - XHS Login Helper (本地)            ║
╠══════════════════════════════════════════════════════════════╣
║  1. Chromium 窗口已打开，请在窗口中完成小红书登录             ║
║  2. 登录成功后，在另一终端创建触发文件以保存会话               ║
║  3. 或若本终端支持输入，可直接按 Enter 保存                   ║
╚══════════════════════════════════════════════════════════════╝
"""

STATE_PATH = _STATE_PATH


def run_cmd(args: list[str], check: bool = False) -> subprocess.CompletedProcess:
    """执行 agent-browser 命令，捕获输出。使用 shell=True 确保 npx 可从 PATH 找到。"""
    full_args = [*CMD_BASE, *SESSION_ARGS, *args]
    cmd_str = " ".join(f'"{a}"' if " " in str(a) else str(a) for a in full_args)
    print(f"[CMD] {cmd_str}")
    return subprocess.run(cmd_str, capture_output=True, text=True, check=check, shell=True)


def check_agent_browser() -> bool:
    """确认 agent-browser 可用。"""
    try:
        # 使用 shell=True 确保 npx 可从 PATH 中找到（nvm 等环境）
        cmd = " ".join([*CMD_BASE, "--version"])
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        print(f"[INFO] agent-browser: {result.stdout.strip() or result.stderr.strip()}")
        return result.returncode == 0
    except Exception as e:
        print(f"[ERROR] agent-browser 未找到: {e}")
        return False


def open_xhs() -> bool:
    """打开小红书首页。agent-browser open 会阻塞直到浏览器关闭，故用 Popen 后台启动。"""
    print(f"\n[INFO] 正在打开 {XHS_URL}...")
    full_args = [*CMD_BASE, *SESSION_ARGS, "--headed", "open", XHS_URL]
    cmd_str = " ".join(f'"{a}"' if " " in str(a) else str(a) for a in full_args)
    print(f"[CMD] {cmd_str}")
    subprocess.Popen(cmd_str, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5)  # 等待 Chromium 启动
    if os.path.exists("/.dockerenv"):
        print("[INFO] Chromium 已启动，请在 http://localhost:6080 查看。")
    else:
        print("[INFO] Chromium 窗口应已打开，请在窗口中完成登录。")
    return True


def wait_for_user_login() -> None:
    """
    等待用户完成登录操作，通过文件触发保存。
    Docker 下 docker-compose up 不连接 stdin，需在另一终端 touch 触发文件。
    """
    # 清除残留触发文件
    if os.path.exists(TRIGGER_FILE):
        os.remove(TRIGGER_FILE)

    banner = BANNER_DOCKER if os.path.exists("/.dockerenv") else BANNER_LOCAL
    print(banner)
    print("=" * 64)
    print("  登录完成后，请在另一个终端执行以下命令触发保存：")
    print()
    if os.path.exists("/.dockerenv"):
        print("    docker exec xhs-login touch /app/data/xhs_login_trigger")
    else:
        # 本地模式：Windows 用 type nul，Unix 用 touch
        if platform.system() == "Windows":
            print(f'    New-Item -Path "{TRIGGER_FILE}" -ItemType File -Force')
        else:
            print(f"    touch \"{TRIGGER_FILE}\"")
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
    screenshot_dir = os.path.dirname(STATE_PATH)
    os.makedirs(screenshot_dir, exist_ok=True)
    screenshot_path = os.path.join(screenshot_dir, "xhs_login_verify.png")
    print(f"\n[INFO] 截图验证登录状态: {screenshot_path}")
    result = subprocess.run(
        " ".join([*CMD_BASE, *SESSION_ARGS, "screenshot", f'"{screenshot_path}"']),
        capture_output=True, text=True, shell=True
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
    print("\n  现在可以运行爬虫（在项目根目录执行）：")
    if os.path.exists("/.dockerenv"):
        print('  docker exec -it nat-app bash -c "nat run --config_file workflow_scraper.yaml --input \'请现在开始执行采集任务。\'"')
    else:
        print('  nat run --config_file workflow_scraper.yaml --input "请现在开始执行采集任务。"')
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
