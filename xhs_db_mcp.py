"""
xhs_db_mcp.py
-------------
小红书爬取数据的 PostgreSQL 存储 FastMCP 服务。
供 NAT react_agent（workflow_scraper.yaml）调用，将爬取到的
帖子、用户、评论等结构化数据持久化到 PostgreSQL。

暴露的 MCP 工具：
  save_post        - 保存/更新一条帖子
  save_user        - 保存/更新一个用户
  save_comment     - 保存一条评论
  start_session    - 开始一次搜索会话，返回 session_id
  finish_session   - 结束会话，记录统计结果
  query_posts      - 按关键词/作者等条件查询帖子
  query_users      - 查询用户信息
  get_db_stats     - 获取数据库整体统计信息

依赖环境变量：
  POSTGRES_HOST     - 数据库主机（默认 localhost，Docker 中为 postgres）
  POSTGRES_PORT     - 端口（Docker 默认 5432；本地非 Docker 且未设置时默认 15432）
  POSTGRES_DB       - 数据库名（默认 xhs_data）
  POSTGRES_USER     - 用户名（默认 xhs_user）
  POSTGRES_PASSWORD - 密码

运行方式（NAT 通过 workflow_scraper.yaml 自动管理）：
  python xhs_db_mcp.py
"""

import json
import logging
import os
from datetime import datetime

import psycopg2
import psycopg2.extras
from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

mcp = FastMCP("XHS Database")


# -----------------------------------------------------------------------
# 数据库连接
# -----------------------------------------------------------------------

def _default_postgres_host():
    """在 Docker 中若未设置 POSTGRES_HOST，使用 postgres 服务名；否则 localhost。"""
    if os.environ.get("POSTGRES_HOST"):
        return os.environ.get("POSTGRES_HOST")
    # Docker 环境下通常存在 /.dockerenv 或 /app/data
    if os.path.exists("/.dockerenv") or os.path.exists("/app/data"):
        return "postgres"
    return "localhost"


def _default_postgres_port() -> int:
    """本地非 Docker 且未设置 POSTGRES_PORT 时，默认使用 15432（避免与系统 5432 冲突）。"""
    if os.environ.get("POSTGRES_PORT"):
        try:
            return int(os.environ.get("POSTGRES_PORT"))
        except (ValueError, TypeError):
            pass
    # Docker 内默认 5432；本地（无 /.dockerenv）默认 15432
    if os.path.exists("/.dockerenv") or os.path.exists("/app/data"):
        return 5432
    return 15432


def _get_conn():
    """创建 PostgreSQL 连接。每次调用创建新连接（MCP 短生命周期，无需连接池）。"""
    port = _default_postgres_port()
    dbname = os.environ.get("POSTGRES_DB", "xhs_data")
    user = os.environ.get("POSTGRES_USER", "xhs_user")
    password = os.environ.get("POSTGRES_PASSWORD", "xhs_secure_pass")
    hosts = [_default_postgres_host()]
    # 若默认用 localhost 且可能处于 Docker，失败时尝试 postgres 服务名
    if hosts[0] == "localhost" and (os.path.exists("/.dockerenv") or os.path.exists("/app/data")):
        hosts.append("postgres")
    err = None
    for host in hosts:
        try:
            return psycopg2.connect(
                host=host,
                port=port,
                dbname=dbname,
                user=user,
                password=password,
                connect_timeout=10,
            )
        except psycopg2.OperationalError as e:
            err = e
    raise err


def _safe_int(value, default: int = 0) -> int:
    """安全转换为整数，忽略无法解析的值。"""
    try:
        return int(str(value).replace(",", "").strip()) if value else default
    except (ValueError, TypeError):
        return default


def _safe_str(value, max_len: int = None, default: str = "") -> str:
    """安全转换为字符串，可选截断。"""
    result = str(value).strip() if value else default
    return result[:max_len] if max_len and len(result) > max_len else result


def _safe_json(value) -> dict:
    """安全转换为 JSON 对象（dict）。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {"raw": value}
        except Exception:
            return {"raw": value}
    return {}


# -----------------------------------------------------------------------
# MCP 工具：搜索会话管理
# -----------------------------------------------------------------------

@mcp.tool()
def start_session(search_keyword: str) -> str:
    """
    开始一次小红书搜索采集会话。
    在每次运行爬虫前调用，返回 session_id 用于关联本次采集的所有数据。

    Args:
        search_keyword: 本次搜索使用的关键词，例如"保险"或"重疾险"

    Returns:
        session_id 字符串，后续操作中传入此 ID
    """
    try:
        conn = _get_conn()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO xhs_search_sessions (search_keyword, status)
                VALUES (%s, 'running')
                RETURNING session_id::text, id
                """,
                (_safe_str(search_keyword, 200),),
            )
            row = cur.fetchone()
            session_id = row[0]
            db_id = row[1]
        conn.close()
        logger.info("开始搜索会话：keyword=%s, session_id=%s", search_keyword, session_id)
        return f"会话已创建。session_id={session_id}（数据库 id={db_id}）。请在后续所有 save_post/save_user 调用中记录此关键词。"
    except Exception as exc:
        logger.error("start_session 失败：%s", exc)
        return f"错误：{exc}"


@mcp.tool()
def finish_session(
    search_keyword: str,
    posts_found: int,
    users_found: int = 0,
    comments_found: int = 0,
    notes: str = "",
) -> str:
    """
    结束搜索会话，记录本次采集的汇总统计。
    在每个关键词的采集流程结束后调用。

    Args:
        search_keyword: 与 start_session 一致的关键词
        posts_found: 本次找到并保存的帖子数
        users_found: 本次发现并保存的用户数（可为 0）
        comments_found: 本次采集的评论数（可为 0）
        notes: 备注信息（如遇到的问题、页面限制等）
    """
    try:
        conn = _get_conn()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE xhs_search_sessions
                SET
                    status         = 'completed',
                    posts_found    = %s,
                    users_found    = %s,
                    comments_found = %s,
                    notes          = %s,
                    finished_at    = NOW()
                WHERE search_keyword = %s AND status = 'running'
                """,
                (
                    _safe_int(posts_found),
                    _safe_int(users_found),
                    _safe_int(comments_found),
                    _safe_str(notes, 2000),
                    _safe_str(search_keyword, 200),
                ),
            )
            updated = cur.rowcount
        conn.close()
        logger.info("结束搜索会话：keyword=%s, posts=%d", search_keyword, posts_found)
        return (
            f"会话结束。已更新 {updated} 条会话记录。\n"
            f"关键词：{search_keyword} | 帖子：{posts_found} | 用户：{users_found} | 评论：{comments_found}"
        )
    except Exception as exc:
        logger.error("finish_session 失败：%s", exc)
        return f"错误：{exc}"


# -----------------------------------------------------------------------
# MCP 工具：多平台搜索会话管理
# -----------------------------------------------------------------------

@mcp.tool()
def start_social_session(platform: str, search_keyword: str) -> str:
    """开始一次多平台采集会话。"""
    if not platform:
        return "错误：platform 不能为空。"
    try:
        conn = _get_conn()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO social_search_sessions (platform, search_keyword, status)
                VALUES (%s, %s, 'running')
                RETURNING session_id::text, id
                """,
                (_safe_str(platform, 32), _safe_str(search_keyword, 255)),
            )
            row = cur.fetchone()
        conn.close()
        return f"多平台会话已创建。platform={platform}, session_id={row[0]}（数据库 id={row[1]}）"
    except Exception as exc:
        logger.error("start_social_session 失败：%s", exc)
        return f"错误：{exc}"


@mcp.tool()
def finish_social_session(
    platform: str,
    search_keyword: str,
    posts_found: int,
    users_found: int = 0,
    comments_found: int = 0,
    leads_found: int = 0,
    comment_success_rate: float = 0,
    comment_blocked_rate: float = 0,
    login_required_count: int = 0,
    notes: str = "",
) -> str:
    """结束一次多平台采集会话并记录结构化指标。"""
    try:
        conn = _get_conn()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE social_search_sessions
                SET
                    status               = 'completed',
                    posts_found          = %s,
                    users_found          = %s,
                    comments_found       = %s,
                    leads_found          = %s,
                    comment_success_rate = %s,
                    comment_blocked_rate = %s,
                    login_required_count = %s,
                    notes                = %s,
                    finished_at          = NOW()
                WHERE platform = %s AND search_keyword = %s AND status = 'running'
                """,
                (
                    _safe_int(posts_found),
                    _safe_int(users_found),
                    _safe_int(comments_found),
                    _safe_int(leads_found),
                    float(comment_success_rate or 0),
                    float(comment_blocked_rate or 0),
                    _safe_int(login_required_count),
                    _safe_str(notes, 2000),
                    _safe_str(platform, 32),
                    _safe_str(search_keyword, 255),
                ),
            )
            updated = cur.rowcount
        conn.close()
        return f"多平台会话结束。platform={platform}，已更新 {updated} 条记录。"
    except Exception as exc:
        logger.error("finish_social_session 失败：%s", exc)
        return f"错误：{exc}"


# -----------------------------------------------------------------------
# MCP 工具：保存数据
# -----------------------------------------------------------------------

@mcp.tool()
def save_post(
    post_id: str,
    title: str,
    content: str,
    url: str,
    author_name: str = "",
    author_id: str = "",
    likes_count: int = 0,
    comments_count: int = 0,
    collects_count: int = 0,
    tags: str = "",
    search_keyword: str = "保险",
    cover_image_url: str = "",
    post_type: str = "note",
) -> str:
    """
    保存或更新一条小红书帖子到 PostgreSQL。
    若 post_id 已存在，则更新互动数据和内容（UPSERT）。

    Args:
        post_id: 帖子唯一标识（从 URL 中提取，如 /explore/<post_id>）
        title: 帖子标题
        content: 帖子正文内容
        url: 帖子完整 URL
        author_name: 作者昵称
        author_id: 作者唯一 ID（若可获取）
        likes_count: 点赞数（数字，若显示如"1.2万"请转换为整数12000）
        comments_count: 评论数
        collects_count: 收藏数
        tags: 话题标签，以逗号分隔，如"#重疾险,#保险攻略"
        search_keyword: 发现该帖子时使用的搜索关键词
        cover_image_url: 封面图链接（可选）
        post_type: 内容类型，note/video/live（默认 note）
    """
    if not post_id or not post_id.strip():
        return "错误：post_id 不能为空。"

    tags_list = [t.strip().lstrip("#") for t in tags.split(",") if t.strip()] if tags else []

    try:
        conn = _get_conn()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO xhs_posts (
                    post_id, title, content, url, cover_image_url,
                    author_name, author_id,
                    likes_count, comments_count, collects_count,
                    tags, search_keyword, post_type
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s
                )
                ON CONFLICT (post_id) DO UPDATE SET
                    title           = EXCLUDED.title,
                    content         = EXCLUDED.content,
                    likes_count     = EXCLUDED.likes_count,
                    comments_count  = EXCLUDED.comments_count,
                    collects_count  = EXCLUDED.collects_count,
                    tags            = EXCLUDED.tags,
                    author_name     = EXCLUDED.author_name,
                    author_id       = EXCLUDED.author_id,
                    last_updated_at = NOW()
                RETURNING id
                """,
                (
                    _safe_str(post_id, 150),
                    _safe_str(title),
                    _safe_str(content),
                    _safe_str(url),
                    _safe_str(cover_image_url),
                    _safe_str(author_name, 200),
                    _safe_str(author_id, 100),
                    _safe_int(likes_count),
                    _safe_int(comments_count),
                    _safe_int(collects_count),
                    tags_list,
                    _safe_str(search_keyword, 200),
                    _safe_str(post_type, 20),
                ),
            )
            db_id = cur.fetchone()[0]
        conn.close()
        logger.info("保存帖子：%s（id=%d）", post_id, db_id)
        return f"帖子已保存。post_id={post_id}, 数据库 id={db_id}, 标签={tags_list}"
    except Exception as exc:
        logger.error("save_post 失败：%s", exc)
        return f"错误：{exc}"


@mcp.tool()
def save_user(
    user_id: str,
    username: str,
    profile_url: str = "",
    bio: str = "",
    followers_count: int = 0,
    following_count: int = 0,
    posts_count: int = 0,
    is_verified: bool = False,
) -> str:
    """
    保存或更新一个小红书用户信息。
    若 user_id 已存在，则更新粉丝数等信息（UPSERT）。

    Args:
        user_id: 用户唯一 ID（从主页 URL 提取）
        username: 用户昵称
        profile_url: 用户主页链接
        bio: 个人简介
        followers_count: 粉丝数
        following_count: 关注数
        posts_count: 发帖数（页面可见的总数）
        is_verified: 是否认证账号（蓝 V 等）
    """
    if not user_id or not user_id.strip():
        return "错误：user_id 不能为空。"

    try:
        conn = _get_conn()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO xhs_users (
                    user_id, username, profile_url, bio,
                    followers_count, following_count, posts_count, is_verified
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    username        = EXCLUDED.username,
                    bio             = EXCLUDED.bio,
                    followers_count = EXCLUDED.followers_count,
                    following_count = EXCLUDED.following_count,
                    posts_count     = EXCLUDED.posts_count,
                    is_verified     = EXCLUDED.is_verified,
                    last_updated_at = NOW()
                RETURNING id
                """,
                (
                    _safe_str(user_id, 100),
                    _safe_str(username, 200),
                    _safe_str(profile_url),
                    _safe_str(bio),
                    _safe_int(followers_count),
                    _safe_int(following_count),
                    _safe_int(posts_count),
                    bool(is_verified),
                ),
            )
            db_id = cur.fetchone()[0]
        conn.close()
        logger.info("保存用户：%s（%s）id=%d", username, user_id, db_id)
        return f"用户已保存。user_id={user_id}, username={username}, 粉丝数={followers_count}, 数据库 id={db_id}"
    except Exception as exc:
        logger.error("save_user 失败：%s", exc)
        return f"错误：{exc}"


@mcp.tool()
def save_comment(
    comment_id: str,
    post_id: str,
    content: str,
    author_name: str = "",
    author_id: str = "",
    likes_count: int = 0,
    is_top_comment: bool = False,
) -> str:
    """
    保存一条帖子评论。评论通常反映真实用户需求，是重要数据。

    Args:
        comment_id: 评论唯一 ID
        post_id: 所属帖子的 post_id（需已用 save_post 保存）
        content: 评论内容
        author_name: 评论者昵称
        author_id: 评论者 ID（若可获取）
        likes_count: 评论获得的点赞数
        is_top_comment: 是否为置顶/热门评论
    """
    if not comment_id or not content:
        return "错误：comment_id 和 content 不能为空。"

    try:
        conn = _get_conn()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO xhs_comments (
                    comment_id, post_id, content,
                    author_name, author_id,
                    likes_count, is_top_comment
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (comment_id) DO UPDATE SET
                    likes_count    = EXCLUDED.likes_count,
                    is_top_comment = EXCLUDED.is_top_comment
                RETURNING id
                """,
                (
                    _safe_str(comment_id, 150),
                    _safe_str(post_id, 150),
                    _safe_str(content),
                    _safe_str(author_name, 200),
                    _safe_str(author_id, 100),
                    _safe_int(likes_count),
                    bool(is_top_comment),
                ),
            )
        conn.close()
        logger.info("保存评论：comment_id=%s, post_id=%s", comment_id, post_id)
        return f"评论已保存。comment_id={comment_id}"
    except Exception as exc:
        logger.error("save_comment 失败：%s", exc)
        return f"错误：{exc}"


@mcp.tool()
def save_social_user(
    platform: str,
    user_id: str,
    username: str,
    profile_url: str = "",
    bio: str = "",
    followers_count: int = 0,
    following_count: int = 0,
    posts_count: int = 0,
    is_verified: bool = False,
    extra: str = "",
) -> str:
    """保存或更新多平台用户。"""
    if not platform or not user_id:
        return "错误：platform 和 user_id 不能为空。"
    try:
        conn = _get_conn()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO social_users (
                    platform, user_id, username, profile_url, bio,
                    followers_count, following_count, posts_count, is_verified, extra
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (platform, user_id) DO UPDATE SET
                    username        = EXCLUDED.username,
                    profile_url     = EXCLUDED.profile_url,
                    bio             = EXCLUDED.bio,
                    followers_count = EXCLUDED.followers_count,
                    following_count = EXCLUDED.following_count,
                    posts_count     = EXCLUDED.posts_count,
                    is_verified     = EXCLUDED.is_verified,
                    extra           = EXCLUDED.extra,
                    last_updated_at = NOW()
                RETURNING id
                """,
                (
                    _safe_str(platform, 32),
                    _safe_str(user_id, 150),
                    _safe_str(username, 255),
                    _safe_str(profile_url),
                    _safe_str(bio),
                    _safe_int(followers_count),
                    _safe_int(following_count),
                    _safe_int(posts_count),
                    bool(is_verified),
                    psycopg2.extras.Json(_safe_json(extra)),
                ),
            )
            db_id = cur.fetchone()[0]
        conn.close()
        return f"多平台用户已保存。platform={platform}, user_id={user_id}, id={db_id}"
    except Exception as exc:
        logger.error("save_social_user 失败：%s", exc)
        return f"错误：{exc}"


@mcp.tool()
def save_social_post(
    platform: str,
    post_id: str,
    title: str = "",
    content: str = "",
    url: str = "",
    author_name: str = "",
    author_id: str = "",
    likes_count: int = 0,
    comments_count: int = 0,
    collects_count: int = 0,
    shares_count: int = 0,
    tags: str = "",
    search_keyword: str = "",
    cover_image_url: str = "",
    post_type: str = "post",
    extra: str = "",
) -> str:
    """保存或更新多平台帖子。"""
    if not platform or not post_id:
        return "错误：platform 和 post_id 不能为空。"
    tags_list = [t.strip().lstrip("#") for t in tags.split(",") if t.strip()] if tags else []
    try:
        conn = _get_conn()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO social_posts (
                    platform, post_id, title, content, url, post_type, cover_image_url,
                    likes_count, comments_count, collects_count, shares_count,
                    author_id, author_name, tags, search_keyword, extra
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                ON CONFLICT (platform, post_id) DO UPDATE SET
                    title           = EXCLUDED.title,
                    content         = EXCLUDED.content,
                    likes_count     = EXCLUDED.likes_count,
                    comments_count  = EXCLUDED.comments_count,
                    collects_count  = EXCLUDED.collects_count,
                    shares_count    = EXCLUDED.shares_count,
                    author_id       = EXCLUDED.author_id,
                    author_name     = EXCLUDED.author_name,
                    tags            = EXCLUDED.tags,
                    search_keyword  = EXCLUDED.search_keyword,
                    extra           = EXCLUDED.extra,
                    last_updated_at = NOW()
                RETURNING id
                """,
                (
                    _safe_str(platform, 32),
                    _safe_str(post_id, 200),
                    _safe_str(title),
                    _safe_str(content),
                    _safe_str(url),
                    _safe_str(post_type, 32),
                    _safe_str(cover_image_url),
                    _safe_int(likes_count),
                    _safe_int(comments_count),
                    _safe_int(collects_count),
                    _safe_int(shares_count),
                    _safe_str(author_id, 150),
                    _safe_str(author_name, 255),
                    tags_list,
                    _safe_str(search_keyword, 255),
                    psycopg2.extras.Json(_safe_json(extra)),
                ),
            )
            db_id = cur.fetchone()[0]
        conn.close()
        return f"多平台帖子已保存。platform={platform}, post_id={post_id}, id={db_id}"
    except Exception as exc:
        logger.error("save_social_post 失败：%s", exc)
        return f"错误：{exc}"


@mcp.tool()
def save_social_comment(
    platform: str,
    comment_id: str,
    post_id: str,
    content: str,
    author_name: str = "",
    author_id: str = "",
    likes_count: int = 0,
    is_top_comment: bool = False,
    source_type: str = "comment",
    extra: str = "",
) -> str:
    """保存或更新多平台评论。"""
    if not platform or not comment_id or not post_id:
        return "错误：platform/comment_id/post_id 不能为空。"
    try:
        conn = _get_conn()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO social_comments (
                    platform, comment_id, post_id, author_id, author_name,
                    content, likes_count, is_top_comment, source_type, extra
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (platform, comment_id) DO UPDATE SET
                    likes_count    = EXCLUDED.likes_count,
                    is_top_comment = EXCLUDED.is_top_comment,
                    source_type    = EXCLUDED.source_type,
                    extra          = EXCLUDED.extra
                RETURNING id
                """,
                (
                    _safe_str(platform, 32),
                    _safe_str(comment_id, 200),
                    _safe_str(post_id, 200),
                    _safe_str(author_id, 150),
                    _safe_str(author_name, 255),
                    _safe_str(content),
                    _safe_int(likes_count),
                    bool(is_top_comment),
                    _safe_str(source_type, 32),
                    psycopg2.extras.Json(_safe_json(extra)),
                ),
            )
            db_id = cur.fetchone()[0]
        conn.close()
        return f"多平台评论已保存。platform={platform}, comment_id={comment_id}, id={db_id}"
    except Exception as exc:
        logger.error("save_social_comment 失败：%s", exc)
        return f"错误：{exc}"


# -----------------------------------------------------------------------
# MCP 工具：查询数据
# -----------------------------------------------------------------------

@mcp.tool()
def query_posts(
    keyword: str = "",
    author_name: str = "",
    tag: str = "",
    min_likes: int = 0,
    limit: int = 10,
) -> str:
    """
    查询数据库中的小红书帖子。支持多条件组合筛选。

    Args:
        keyword: 在标题和正文中搜索的关键词（空则不过滤）
        author_name: 按作者名称筛选（空则不过滤）
        tag: 按话题标签筛选，如"重疾险"（空则不过滤）
        min_likes: 最低点赞数过滤（0 = 不过滤）
        limit: 返回条数上限（默认 10，最大 50）
    """
    conditions = ["1=1"]
    params: list = []

    if keyword:
        conditions.append(
            "to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(content,'')) "
            "@@ plainto_tsquery('simple', %s)"
        )
        params.append(keyword)

    if author_name:
        conditions.append("author_name ILIKE %s")
        params.append(f"%{author_name}%")

    if tag:
        conditions.append("%s = ANY(tags)")
        params.append(tag.lstrip("#"))

    if min_likes > 0:
        conditions.append("likes_count >= %s")
        params.append(min_likes)

    limit_val = min(int(limit), 50)
    params.append(limit_val)

    sql = f"""
        SELECT post_id, title, LEFT(content, 150) AS preview,
               author_name, likes_count, comments_count, tags,
               search_keyword, collected_at::date
        FROM xhs_posts
        WHERE {' AND '.join(conditions)}
        ORDER BY likes_count DESC
        LIMIT %s
    """

    try:
        conn = _get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        conn.close()

        if not rows:
            return "未找到符合条件的帖子。"

        lines = [f"共找到 {len(rows)} 条帖子（最多显示 {limit_val} 条）：\n"]
        for i, row in enumerate(rows, 1):
            lines.append(
                f"{i}. 【{row['title'] or '（无标题）'}】\n"
                f"   作者：{row['author_name']} | 点赞：{row['likes_count']} | 评论：{row['comments_count']}\n"
                f"   标签：{', '.join(row['tags'] or [])}\n"
                f"   预览：{row['preview']}...\n"
                f"   采集日期：{row['collected_at']}\n"
            )
        return "\n".join(lines)
    except Exception as exc:
        logger.error("query_posts 失败：%s", exc)
        return f"查询失败：{exc}"


@mcp.tool()
def query_users(
    username: str = "",
    min_followers: int = 0,
    limit: int = 10,
) -> str:
    """
    查询数据库中的小红书用户。

    Args:
        username: 按用户名模糊匹配（空则不过滤）
        min_followers: 最低粉丝数过滤
        limit: 返回条数上限（默认 10）
    """
    conditions = ["1=1"]
    params: list = []

    if username:
        conditions.append("username ILIKE %s")
        params.append(f"%{username}%")

    if min_followers > 0:
        conditions.append("followers_count >= %s")
        params.append(min_followers)

    limit_val = min(int(limit), 50)
    params.append(limit_val)

    sql = f"""
        SELECT u.user_id, u.username, u.followers_count, u.bio,
               u.profile_url, u.is_verified,
               COUNT(p.id) AS post_count
        FROM xhs_users u
        LEFT JOIN xhs_posts p ON p.author_id = u.user_id
        WHERE {' AND '.join(conditions)}
        GROUP BY u.id
        ORDER BY u.followers_count DESC
        LIMIT %s
    """

    try:
        conn = _get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        conn.close()

        if not rows:
            return "未找到符合条件的用户。"

        lines = [f"找到 {len(rows)} 位用户：\n"]
        for i, row in enumerate(rows, 1):
            verified_mark = "✓认证" if row["is_verified"] else ""
            lines.append(
                f"{i}. {row['username']} {verified_mark}\n"
                f"   粉丝：{row['followers_count']:,} | 数据库帖子数：{row['post_count']}\n"
                f"   简介：{row['bio'][:80] if row['bio'] else '（无）'}\n"
                f"   主页：{row['profile_url']}\n"
            )
        return "\n".join(lines)
    except Exception as exc:
        logger.error("query_users 失败：%s", exc)
        return f"查询失败：{exc}"


@mcp.tool()
def get_db_stats() -> str:
    """
    获取小红书数据库的整体统计信息。
    包括帖子总数、用户总数、各关键词分布、最新采集时间等。
    用于了解当前数据库状态和数据量。
    """
    try:
        conn = _get_conn()
        stats = {}

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM xhs_posts")
            stats["total_posts"] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM xhs_users")
            stats["total_users"] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM xhs_comments")
            stats["total_comments"] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM xhs_search_sessions")
            stats["total_sessions"] = cur.fetchone()[0]

            cur.execute("SELECT MAX(collected_at) FROM xhs_posts")
            latest = cur.fetchone()[0]
            stats["latest_collection"] = str(latest)[:19] if latest else "无数据"

            cur.execute("""
                SELECT search_keyword, COUNT(*) as cnt
                FROM xhs_posts
                GROUP BY search_keyword
                ORDER BY cnt DESC
                LIMIT 10
            """)
            keyword_rows = cur.fetchall()
            stats["keyword_distribution"] = {r[0]: r[1] for r in keyword_rows}

            cur.execute("SELECT AVG(likes_count) FROM xhs_posts WHERE likes_count > 0")
            avg_likes = cur.fetchone()[0]
            stats["avg_likes"] = round(float(avg_likes), 1) if avg_likes else 0

            cur.execute("SELECT COUNT(*) FROM social_posts")
            stats["social_posts"] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM social_users")
            stats["social_users"] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM social_comments")
            stats["social_comments"] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM social_search_sessions")
            stats["social_sessions"] = cur.fetchone()[0]

        conn.close()

        return (
            f"=== 小红书数据库统计 ===\n"
            f"帖子总数：{stats['total_posts']:,}\n"
            f"用户总数：{stats['total_users']:,}\n"
            f"评论总数：{stats['total_comments']:,}\n"
            f"搜索会话数：{stats['total_sessions']:,}\n"
            f"最新采集时间：{stats['latest_collection']}\n"
            f"帖子平均点赞：{stats['avg_likes']}\n"
            f"\n关键词分布：\n"
            + "\n".join(f"  {kw}：{cnt} 条" for kw, cnt in stats["keyword_distribution"].items())
            + (
                f"\n\n=== 多平台原始数据统计 ===\n"
                f"social_posts：{stats['social_posts']:,}\n"
                f"social_users：{stats['social_users']:,}\n"
                f"social_comments：{stats['social_comments']:,}\n"
                f"social_sessions：{stats['social_sessions']:,}"
            )
        )
    except Exception as exc:
        logger.error("get_db_stats 失败：%s", exc)
        return f"查询失败：{exc}。请确认 PostgreSQL 服务已启动。"


@mcp.tool()
def save_lead(
    user_id: str,
    username: str,
    lead_score: int,
    lead_reason: str,
    source_post_id: str = "",
    source_keyword: str = "",
    profile_url: str = "",
    contact_hint: str = "",
    insurance_interest: str = "",
    platform: str = "xhs",
    source_type: str = "post_comment",
    source_url: str = "",
    dedup_key: str = "",
) -> str:
    """
    保存一条潜在客户线索到 leads 表。
    由 AI 助理在识别出有保险需求的用户后调用。

    Args:
        user_id: 小红书用户唯一 ID
        username: 用户昵称
        lead_score: 意向评分 1-5（5=主动求推荐保险顾问，4=提到人生大事/明确需求，
                    3=讨论理财/储蓄，2=关注保险内容，1=泛泛浏览）
        lead_reason: AI 判断依据，如"在评论中询问香港重疾险推荐"
        source_post_id: 发现该用户的来源帖子 ID
        source_keyword: 触发该次搜索的关键词
        profile_url: 用户主页链接
        contact_hint: 联系线索，如"评论中留了微信/求私信"
        insurance_interest: 感兴趣的险种，逗号分隔，如"重疾险,医疗险"
    """
    if not user_id or not username:
        return "错误：user_id 和 username 不能为空。"
    score = max(1, min(5, _safe_int(lead_score, 1)))
    interests = [t.strip() for t in insurance_interest.split(",") if t.strip()] if insurance_interest else []

    try:
        conn = _get_conn()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leads (
                    user_id, username, profile_url, lead_score, lead_reason,
                    contact_hint, source_post_id, source_keyword, insurance_interest,
                    platform, source_type, source_url, dedup_key
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (platform, user_id, source_post_id) DO UPDATE SET
                    lead_score         = GREATEST(leads.lead_score, EXCLUDED.lead_score),
                    lead_reason        = EXCLUDED.lead_reason,
                    contact_hint       = EXCLUDED.contact_hint,
                    insurance_interest = EXCLUDED.insurance_interest,
                    source_type        = EXCLUDED.source_type,
                    source_url         = EXCLUDED.source_url,
                    dedup_key          = EXCLUDED.dedup_key,
                    last_updated_at    = NOW()
                RETURNING id, lead_score
                """,
                (
                    _safe_str(user_id, 100),
                    _safe_str(username, 200),
                    _safe_str(profile_url),
                    score,
                    _safe_str(lead_reason),
                    _safe_str(contact_hint),
                    _safe_str(source_post_id, 150),
                    _safe_str(source_keyword, 200),
                    interests,
                    _safe_str(platform, 32),
                    _safe_str(source_type, 32),
                    _safe_str(source_url),
                    _safe_str(dedup_key, 255),
                ),
            )
            row = cur.fetchone()
            db_id, final_score = row[0], row[1]
        conn.close()
        logger.info("保存潜在客户：%s（%s）评分=%d", username, user_id, final_score)
        return f"潜在客户已记录。user_id={user_id}, username={username}, 评分={final_score}/5, 数据库 id={db_id}"
    except Exception as exc:
        logger.error("save_lead 失败：%s", exc)
        return f"错误：{exc}"


@mcp.tool()
def save_social_lead(
    platform: str,
    user_id: str,
    username: str,
    lead_score: int,
    lead_reason: str,
    source_post_id: str = "",
    source_keyword: str = "",
    profile_url: str = "",
    contact_hint: str = "",
    insurance_interest: str = "",
    source_type: str = "post_comment",
    source_url: str = "",
    dedup_key: str = "",
) -> str:
    """多平台 lead 写入包装器（复用 save_lead）。"""
    return save_lead(
        user_id=user_id,
        username=username,
        lead_score=lead_score,
        lead_reason=lead_reason,
        source_post_id=source_post_id,
        source_keyword=source_keyword,
        profile_url=profile_url,
        contact_hint=contact_hint,
        insurance_interest=insurance_interest,
        platform=platform,
        source_type=source_type,
        source_url=source_url,
        dedup_key=dedup_key,
    )


@mcp.tool()
def save_liked_post(
    post_id: str,
    post_url: str = "",
    post_title: str = "",
    liked_reason: str = "",
) -> str:
    """
    记录一条已点赞的帖子，防止重复点赞。
    在成功执行点赞操作后立即调用。

    Args:
        post_id: 帖子唯一 ID
        post_url: 帖子链接
        post_title: 帖子标题
        liked_reason: 点赞原因，如"高质量保险科普内容，互动率高"
    """
    if not post_id:
        return "错误：post_id 不能为空。"
    try:
        conn = _get_conn()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO liked_posts (post_id, post_url, post_title, liked_reason)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (post_id) DO NOTHING
                RETURNING id
                """,
                (
                    _safe_str(post_id, 150),
                    _safe_str(post_url),
                    _safe_str(post_title),
                    _safe_str(liked_reason),
                ),
            )
            row = cur.fetchone()
        conn.close()
        if row:
            logger.info("记录点赞帖子：%s", post_id)
            return f"点赞记录已保存。post_id={post_id}"
        else:
            return f"该帖子已在点赞记录中（之前已点赞）。post_id={post_id}"
    except Exception as exc:
        logger.error("save_liked_post 失败：%s", exc)
        return f"错误：{exc}"


@mcp.tool()
def check_already_liked(post_id: str) -> str:
    """
    检查某帖子是否已被点赞过，避免重复操作。

    Args:
        post_id: 帖子唯一 ID

    Returns:
        "已点赞" 或 "未点赞"
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM liked_posts WHERE post_id = %s", (_safe_str(post_id, 150),))
            exists = cur.fetchone() is not None
        conn.close()
        return "已点赞" if exists else "未点赞"
    except Exception as exc:
        return f"查询失败：{exc}"


@mcp.tool()
def get_leads(
    min_score: int = 1,
    status: str = "new",
    limit: int = 20,
) -> str:
    """
    查询潜在客户列表，供保险代理人查看和跟进。

    Args:
        min_score: 最低意向评分（1-5，默认1=全部）
        status: 状态筛选（new/reviewed/contacted，默认 new）
        limit: 返回条数上限（默认 20）
    """
    try:
        conn = _get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT l.platform, l.user_id, l.username, l.lead_score, l.lead_reason,
                       l.contact_hint, l.insurance_interest, l.source_keyword,
                       l.profile_url, l.status, l.discovered_at::date AS date,
                       COALESCE(xp.title, sp.title, '') AS source_post_title
                FROM leads l
                LEFT JOIN xhs_posts xp ON l.platform = 'xhs' AND xp.post_id = l.source_post_id
                LEFT JOIN social_posts sp ON sp.platform = l.platform AND sp.post_id = l.source_post_id
                WHERE l.lead_score >= %s AND (%s = '' OR l.status = %s)
                ORDER BY l.lead_score DESC, l.discovered_at DESC
                LIMIT %s
                """,
                (max(1, min_score), status, status, min(limit, 100)),
            )
            rows = cur.fetchall()
        conn.close()

        if not rows:
            return f"暂无符合条件的潜在客户（评分>={min_score}, 状态={status}）。"

        lines = [f"=== 潜在客户列表（{len(rows)} 条，评分>={min_score}，状态={status}）===\n"]
        for i, r in enumerate(rows, 1):
            interests = ", ".join(r["insurance_interest"]) if r["insurance_interest"] else "未知"
            lines.append(
                f"{i}. ⭐{'★' * r['lead_score']} [{r['lead_score']}/5] {r['username']}\n"
                f"   平台: {r['platform']}\n"
                f"   原因: {r['lead_reason']}\n"
                f"   险种兴趣: {interests} | 关键词: {r['source_keyword']}\n"
                f"   联系线索: {r['contact_hint'] or '无'}\n"
                f"   来源帖: {r['source_post_title'] or r['source_keyword']}\n"
                f"   主页: {r['profile_url'] or '未知'} | 发现日期: {r['date']}\n"
            )
        return "\n".join(lines)
    except Exception as exc:
        logger.error("get_leads 失败：%s", exc)
        return f"查询失败：{exc}"


if __name__ == "__main__":
    mcp.run()
