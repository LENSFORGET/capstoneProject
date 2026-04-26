"""
email_agent.py — 宏利保险 AI 邮件自动回复服务

工作流程：
  1. 每隔 POLL_INTERVAL_SECONDS 秒轮询 Gmail 收件箱中未读且未标记为
     "AI-Processed" 的邮件
  2. 解析邮件内容（base64url 解码），提取发件人 / 主题 / 正文
  3. 调用 nat-orchestrator /generate 接口，通过 RAG 生成专业保险回复
  4. 使用 gws gmail +reply 将回复发送给客户
  5. 为原邮件添加 "AI-Processed" 标签，防止重复处理

依赖：
  - @googleworkspace/cli (npm)：需以 GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE 认证
  - requests (pip)
  - 环境变量 ORCHESTRATOR_URL、POLL_INTERVAL_SECONDS（可选）
"""

import base64
import json
import logging
import os
import subprocess
import sys
import time

import requests

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://nat-orchestrator:8100")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "30"))
PROCESSED_LABEL_NAME = "AI-Processed"
MAX_EMAILS_PER_POLL = 10
ORCHESTRATOR_TIMEOUT = 120  # orchestrator RAG 响应最长等待秒数
GMAIL_USER = "me"           # gws 用 "me" 代表已认证账户

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("email_agent")


# ---------------------------------------------------------------------------
# gws CLI 调用封装
# ---------------------------------------------------------------------------

def _run_gws(*args: str) -> dict | list:
    """运行 gws 命令，解析 JSON 输出，失败时抛出 RuntimeError。"""
    cmd = ["gws"] + list(args)
    log.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(
            f"gws command failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    raw = result.stdout.strip()
    if not raw:
        return {}
    return json.loads(raw)


def _run_gws_raw(*args: str) -> str:
    """运行 gws 命令，返回原始 stdout（用于回复等不需要解析 JSON 的场景）。"""
    cmd = ["gws"] + list(args)
    log.debug("Running raw: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(
            f"gws command failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Gmail 标签管理
# ---------------------------------------------------------------------------

def _get_or_create_label(label_name: str) -> str:
    """
    查找已有 Gmail 标签的 ID；若不存在则创建，返回标签 ID。
    """
    try:
        data = _run_gws(
            "gmail", "users", "labels", "list",
            "--params", json.dumps({"userId": GMAIL_USER}),
        )
        labels = data.get("labels", [])
        for lbl in labels:
            if lbl.get("name") == label_name:
                log.info("Found existing label '%s' (id=%s)", label_name, lbl["id"])
                return lbl["id"]
    except Exception as exc:
        log.warning("Could not list labels: %s", exc)

    # 标签不存在，创建它
    try:
        new_label = _run_gws(
            "gmail", "users", "labels", "create",
            "--params", json.dumps({"userId": GMAIL_USER}),
            "--json", json.dumps({"name": label_name}),
        )
        label_id = new_label["id"]
        log.info("Created label '%s' (id=%s)", label_name, label_id)
        return label_id
    except Exception as exc:
        raise RuntimeError(f"Failed to create label '{label_name}': {exc}") from exc


def _apply_label(message_id: str, label_id: str) -> None:
    """为指定邮件添加标签。"""
    _run_gws(
        "gmail", "users", "messages", "modify",
        "--params", json.dumps({"userId": GMAIL_USER, "id": message_id}),
        "--json", json.dumps({"addLabelIds": [label_id]}),
    )
    log.debug("Applied label %s to message %s", label_id, message_id)


# ---------------------------------------------------------------------------
# Gmail 邮件获取与解析
# ---------------------------------------------------------------------------

def _list_unread_messages() -> list[dict]:
    """返回收件箱中未被 AI 处理的邮件列表（仅含 id、threadId）。"""
    query = f"-label:{PROCESSED_LABEL_NAME} in:inbox"
    try:
        data = _run_gws(
            "gmail", "users", "messages", "list",
            "--params", json.dumps({
                "userId": GMAIL_USER,
                "q": query,
                "maxResults": MAX_EMAILS_PER_POLL,
            }),
        )
        return data.get("messages", [])
    except Exception as exc:
        log.error("Failed to list messages: %s", exc)
        return []


def _get_message_detail(message_id: str) -> dict:
    """获取单封邮件的完整内容（format=full）。"""
    return _run_gws(
        "gmail", "users", "messages", "get",
        "--params", json.dumps({
            "userId": GMAIL_USER,
            "id": message_id,
            "format": "full",
        }),
    )


def _decode_base64url(data: str) -> str:
    """将 Gmail 返回的 base64url 字符串解码为文本。"""
    # Gmail 使用 URL-safe base64，需补齐 padding
    padded = data.replace("-", "+").replace("_", "/")
    padded += "=" * (4 - len(padded) % 4)
    try:
        return base64.b64decode(padded).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_text_body(payload: dict) -> str:
    """
    递归遍历邮件 payload，优先提取 text/plain 部分；
    若无则尝试 text/html（剥离 HTML 标签）。
    """
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime_type == "text/plain" and body_data:
        return _decode_base64url(body_data)

    if mime_type == "text/html" and body_data:
        # 简单剥离 HTML 标签
        import re
        html = _decode_base64url(body_data)
        text = re.sub(r"<[^>]+>", "", html)
        text = re.sub(r"\s{3,}", "\n\n", text)
        return text.strip()

    # multipart 递归处理
    for part in payload.get("parts", []):
        text = _extract_text_body(part)
        if text:
            return text

    return ""


def _parse_email(message: dict) -> dict:
    """
    从 Gmail API 完整消息对象中提取：
    - message_id: Gmail 消息 ID
    - sender: 发件人地址
    - subject: 邮件主题
    - body: 正文文本
    """
    headers = {
        h["name"].lower(): h["value"]
        for h in message.get("payload", {}).get("headers", [])
    }
    sender = headers.get("from", "Unknown Sender")
    subject = headers.get("subject", "(No Subject)")
    body = _extract_text_body(message.get("payload", {}))
    # 截断过长正文，避免超出 LLM 上下文
    if len(body) > 4000:
        body = body[:4000] + "\n\n[...内容已截断...]"
    return {
        "message_id": message["id"],
        "sender": sender,
        "subject": subject,
        "body": body,
    }


# ---------------------------------------------------------------------------
# Orchestrator RAG 调用
# ---------------------------------------------------------------------------

def _build_prompt(sender: str, subject: str, body: str) -> str:
    """
    构造发送给 orchestrator 的提示词。
    明确要求：检测来信语言（中/英），以相同语言回复；
    使用正式邮件格式（称呼 + 正文 + 署名）。
    """
    return (
        "[邮件自动回复任务]\n"
        "你是宏利保险（Manulife Hong Kong）的 AI 顾问助理。\n"
        "请根据以下客户来信内容，撰写一封专业的保险顾问回复邮件。\n\n"
        "【重要规则】\n"
        "1. 自动检测客户来信语言（繁体中文 / 简体中文 / English），使用完全相同的语言回复。\n"
        "2. 回复格式为正式邮件：称呼开头 → 主体内容 → 礼貌结语 → 署名（宏利保险顾问团队）。\n"
        "3. 根据客户需求，调用 search_insurance 工具检索准确的产品信息后再撰写回复。\n"
        "4. 如涉及具体保费/赔付条款，注明以正式保单文件为准。\n"
        "5. 【格式要求】输出纯文本邮件正文，不得使用 Markdown 符号（无 **粗体**、无 # 标题、无 - 列表符号、无 emoji）。\n\n"
        f"【客户信息】\n"
        f"发件人：{sender}\n"
        f"主题：{subject}\n\n"
        f"【来信内容】\n"
        f"{body}\n\n"
        "请直接输出回复邮件正文（无需任何解释或 Markdown 格式）。"
    )


def _extract_text_from_response(data: dict | list | str) -> str:
    """
    从 orchestrator 返回值中提取纯文本。
    NAT 框架可能将回复包装在不同结构里：
      {"value": "..."} / {"output": "..."} / {"response": "..."} 等
    """
    if isinstance(data, str):
        return data

    if isinstance(data, list):
        # 取最后一个有文本内容的元素
        for item in reversed(data):
            text = _extract_text_from_response(item)
            if text:
                return text
        return ""

    # dict：按优先级尝试常见键名（value 是 NAT tool_calling_agent 的默认输出键）
    for key in ("value", "output", "response", "message", "result", "text", "content"):
        val = data.get(key)
        if val is None:
            continue
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, (dict, list)):
            nested = _extract_text_from_response(val)
            if nested:
                return nested

    # 兜底：返回空字符串（调用方会记录原始 JSON 日志）
    return ""


def _clean_reply(text: str) -> str:
    """
    将 LLM 输出的 Markdown 格式转换为适合邮件正文的纯文本。
    处理：**粗体** → 纯文本、# 标题 → 文字、✅☑ 等符号 → 移除、多余空行压缩。
    """
    import re

    # 移除 Markdown 标题符号（## 标题 → 标题）
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # **粗体** / __粗体__ → 纯文本
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)

    # *斜体* / _斜体_ → 纯文本
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)

    # 移除行首的列表符号（- / * / 1. 等），保留内容
    text = re.sub(r"^[\*\-]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\d+\.\s+", "", text, flags=re.MULTILINE)

    # 移除常见 emoji（保留中英文标点）
    emoji_pattern = re.compile(
        "["
        "\U0001F300-\U0001F9FF"  # 杂项符号与象形文字
        "\U00002700-\U000027BF"  # 装饰符号
        "\U0000FE00-\U0000FE0F"  # 变体选择器
        "\U00002600-\U000026FF"  # 杂项符号
        "\U00002B50\U00002B55"   # 星星/圆圈
        "\U00002714\U00002705"   # ✔ ✅
        "]+",
        flags=re.UNICODE,
    )
    text = emoji_pattern.sub("", text)

    # 压缩超过 2 个的连续空行为 2 个
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _call_orchestrator(prompt: str) -> str:
    """
    调用 nat-orchestrator /generate 接口，返回清理后的纯文本回复。
    """
    url = f"{ORCHESTRATOR_URL.rstrip('/')}/generate"
    try:
        resp = requests.post(
            url,
            json={"input_message": prompt},
            timeout=ORCHESTRATOR_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        text = _extract_text_from_response(data)
        if not text:
            # 兜底调试：记录原始响应，避免把 JSON 发给客户
            log.error("Could not extract text from orchestrator response: %s",
                      json.dumps(data, ensure_ascii=False)[:500])
            raise RuntimeError("Orchestrator returned unrecognized response structure")

        return _clean_reply(text)

    except requests.exceptions.Timeout:
        raise RuntimeError(f"Orchestrator timed out after {ORCHESTRATOR_TIMEOUT}s")
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Orchestrator request failed: {exc}") from exc


# ---------------------------------------------------------------------------
# 发送回复
# ---------------------------------------------------------------------------

def _send_reply(message_id: str, reply_body: str) -> None:
    """
    使用 gws gmail +reply 向客户回复邮件。
    gws 会自动维护邮件线程（thread）。
    """
    _run_gws_raw(
        "gmail", "+reply",
        "--message-id", message_id,
        "--body", reply_body,
    )
    log.info("Reply sent for message %s", message_id)


# ---------------------------------------------------------------------------
# 主处理循环
# ---------------------------------------------------------------------------

def process_email(email_info: dict, processed_label_id: str) -> None:
    """
    处理单封邮件：解析 → 生成回复 → 发送 → 标记已处理。
    每封邮件独立异常处理，不影响其他邮件。
    """
    msg_id = email_info["message_id"]
    sender = email_info["sender"]
    subject = email_info["subject"]
    body = email_info["body"]

    log.info("Processing email | id=%s | from=%s | subject=%s", msg_id, sender, subject)

    if not body.strip():
        log.warning("Email %s has empty body, skipping RAG call.", msg_id)
        _apply_label(msg_id, processed_label_id)
        return

    prompt = _build_prompt(sender, subject, body)
    log.info("Calling orchestrator for email %s ...", msg_id)
    reply_text = _call_orchestrator(prompt)
    log.info("Orchestrator replied (%d chars) for email %s", len(reply_text), msg_id)

    _send_reply(msg_id, reply_text)
    _apply_label(msg_id, processed_label_id)
    log.info("Email %s processed successfully.", msg_id)


def poll_once(processed_label_id: str) -> None:
    """执行一次轮询：获取待处理邮件并逐封处理。"""
    messages = _list_unread_messages()
    if not messages:
        log.debug("No new emails found.")
        return

    log.info("Found %d new email(s) to process.", len(messages))
    for msg_stub in messages:
        msg_id = msg_stub["id"]
        try:
            message = _get_message_detail(msg_id)
            email_info = _parse_email(message)
            process_email(email_info, processed_label_id)
        except Exception as exc:
            log.error("Failed to process email %s: %s", msg_id, exc, exc_info=True)
            # 仍然标记为已处理，避免错误邮件反复触发
            try:
                _apply_label(msg_id, processed_label_id)
            except Exception:
                pass


def main() -> None:
    log.info("=== 宏利保险 AI 邮件自动回复服务启动 ===")
    log.info("Orchestrator: %s", ORCHESTRATOR_URL)
    log.info("Poll interval: %ds | Max per poll: %d", POLL_INTERVAL, MAX_EMAILS_PER_POLL)

    # 确保 "AI-Processed" 标签存在
    log.info("Initializing Gmail label '%s' ...", PROCESSED_LABEL_NAME)
    processed_label_id = _get_or_create_label(PROCESSED_LABEL_NAME)

    log.info("Starting poll loop. Ctrl+C to stop.")
    while True:
        try:
            poll_once(processed_label_id)
        except KeyboardInterrupt:
            log.info("Stopped by user.")
            break
        except Exception as exc:
            log.error("Unexpected error in poll loop: %s", exc, exc_info=True)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
