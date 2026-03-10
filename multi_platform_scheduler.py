import argparse
import json
import random
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PLATFORMS = {
    "zhihu": {
        "display": "知乎",
        "search_url": "https://www.zhihu.com/search?type=content&q={keyword}",
        "login_required": False,
    },
    "reddit": {
        "display": "Reddit",
        "search_url": "https://www.reddit.com/search/?q={keyword}",
        "login_required": False,
    },
    "twitter": {
        "display": "X",
        "search_url": "https://x.com/search?q={keyword}&src=typed_query",
        "login_required": False,
    },
    "bilibili": {
        "display": "B站",
        "search_url": "https://search.bilibili.com/all?keyword={keyword}",
        "login_required": True,
    },
    "weibo": {
        "display": "微博",
        "search_url": "https://s.weibo.com/weibo?q={keyword}",
        "login_required": True,
    },
    "tieba": {
        "display": "贴吧",
        "search_url": "https://tieba.baidu.com/f/search/res?ie=utf-8&qw={keyword}",
        "login_required": False,
    },
    "douyin": {
        "display": "抖音",
        "search_url": "https://www.douyin.com/search/{keyword}",
        "login_required": True,
    },
    "instagram": {
        "display": "Instagram",
        "search_url": "https://www.instagram.com/explore/search/keyword/?q={keyword}",
        "login_required": True,
    },
    "linkedin": {
        "display": "LinkedIn",
        "search_url": "https://www.linkedin.com/search/results/content/?keywords={keyword}",
        "login_required": True,
    },
}

PLATFORM_WAVES = {
    "wave1": ["zhihu", "reddit", "twitter"],
    "wave2": ["bilibili", "weibo", "tieba", "douyin", "instagram", "linkedin"],
    "all": ["zhihu", "reddit", "twitter", "bilibili", "weibo", "tieba", "douyin", "instagram", "linkedin"],
}

KEYWORDS_ZH = [
    "香港保险",
    "重疾险怎么选",
    "医疗险推荐",
    "储蓄险",
    "养老规划",
    "保险规划求助",
    "移民保险",
]

KEYWORDS_EN = [
    "hong kong insurance",
    "critical illness insurance",
    "medical insurance hong kong",
    "retirement planning hong kong",
    "expat insurance hong kong",
    "family protection insurance",
    "wealth planning insurance",
]

ENGLISH_FIRST_PLATFORMS = {"twitter", "reddit", "linkedin", "instagram"}

STATE_FILE = Path("C:/tmp/openclaw/social-rotation.json")
LOG_FILE = Path("C:/tmp/openclaw/social-scheduler.log")
LOCK_FILE = Path("C:/tmp/openclaw/social-scheduler.lock")
NODE_EXE = Path("C:/nvm4w/nodejs/node.exe")
OPENCLAW_MJS = Path("C:/nvm4w/nodejs/node_modules/openclaw/openclaw.mjs")


def log(msg: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"platform_index": 0, "keyword_index": 0, "per_platform_keyword_index": {}}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def pick_platforms(state: dict, wave: str, max_platforms: int) -> list[str]:
    candidates = PLATFORM_WAVES[wave]
    start = state.get("platform_index", 0) % len(candidates)
    ordered = candidates[start:] + candidates[:start]
    selected = ordered[: max(1, min(max_platforms, len(candidates)))]
    state["platform_index"] = (start + len(selected)) % len(candidates)
    return selected


def pick_keyword_for_platform(state: dict, platform: str) -> str:
    per = state.setdefault("per_platform_keyword_index", {})
    keyword_pool = KEYWORDS_EN if platform in ENGLISH_FIRST_PLATFORMS else KEYWORDS_ZH
    idx = per.get(platform, state.get("keyword_index", 0)) % len(keyword_pool)
    per[platform] = (idx + 1) % len(keyword_pool)
    state["keyword_index"] = (state.get("keyword_index", 0) + 1) % max(len(KEYWORDS_ZH), len(KEYWORDS_EN))
    return keyword_pool[idx]


def build_message(platform: str, keyword: str, max_posts: int) -> str:
    conf = PLATFORMS[platform]
    session_name = f"social_{platform}_session"
    login_rule = (
        f"必须复用浏览器会话 {session_name}（扫码登录一次后长期复用）。若检测到登录态缺失，记录 LOGIN_REQUIRED 并结束该平台本轮。"
        if conf["login_required"]
        else f"优先使用公开页面；浏览器会话名使用 {session_name}；若被拦截则记录 COMMENT_BLOCKED 并结束该帖。"
    )
    search_url = conf["search_url"].format(keyword=keyword)
    return (
        f"你是香港保险代理人的潜客挖掘助理。本轮只执行平台：{conf['display']}（platform={platform}）。"
        f"先打开搜索页：{search_url}。处理最多 {max_posts} 条内容。"
        "核心规则：只把评论用户作为默认潜客来源；发帖作者默认不入 lead。"
        "评论不可达时 users_found=0 且禁止写 lead。"
        "保存原始数据到 social_*：save_social_post/save_social_comment/save_social_user；"
        "潜客使用 save_social_lead（platform 必填）。"
        "每条内容输出结构化字段：post_id, entry_method, retry_count, comment_access, block_reason, users_found, leads_saved。"
        "结束时调用 finish_social_session 并输出汇总：platform, posts_total, comment_success_rate, comment_blocked_rate, lead_from_comments_count, login_required_count。"
        f"{login_rule}"
    )


def run_openclaw(message: str, timeout_sec: int) -> tuple[int, str, str]:
    cmd = [
        str(NODE_EXE),
        str(OPENCLAW_MJS),
        "agent",
        "--agent",
        "main",
        "--message",
        message,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        out, err = proc.communicate(timeout=timeout_sec)
        return proc.returncode or 0, out, err
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        return 124, out, (err or "") + "\nTIMEOUT"


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-platform lead collection scheduler")
    parser.add_argument("--wave", choices=["wave1", "wave2", "all"], default="all")
    parser.add_argument("--platform", default="", help="Comma-separated platform ids")
    parser.add_argument("--max-platforms", type=int, default=2)
    parser.add_argument("--max-posts", type=int, default=4)
    parser.add_argument("--timeout-sec", type=int, default=600)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        log("[WARN] scheduler already running, skip this round")
        return 0

    LOCK_FILE.write_text(str(datetime.now().timestamp()), encoding="utf-8")
    try:
        state = load_state()
        if args.platform.strip():
            selected = [p.strip() for p in args.platform.split(",") if p.strip() in PLATFORMS]
        else:
            selected = pick_platforms(state, args.wave, args.max_platforms)

        if not selected:
            print("No valid platform selected.")
            return 1

        log(f"[INFO] Start cycle wave={args.wave} platforms={selected}")
        for platform in selected:
            keyword = pick_keyword_for_platform(state, platform)
            message = build_message(platform, keyword, args.max_posts)
            log(f"[INFO] platform={platform} keyword={keyword}")
            if args.dry_run:
                print(f"[DRY-RUN] {platform} -> {keyword}")
                continue
            code, out, err = run_openclaw(message, args.timeout_sec)
            out_snippet = (out or "")[:4000].replace("\n", " ")
            err_snippet = (err or "")[:2000].replace("\n", " ")
            log(f"[INFO] platform={platform} exit={code} stdout={out_snippet}")
            if err_snippet:
                log(f"[WARN] platform={platform} stderr={err_snippet}")

        save_state(state)
        log("[INFO] End cycle")
        return 0
    finally:
        try:
            if LOCK_FILE.exists():
                LOCK_FILE.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
