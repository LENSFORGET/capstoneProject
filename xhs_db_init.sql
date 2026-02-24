-- =============================================================================
-- 小红书保险内容采集数据库 Schema
-- 数据库：xhs_data
-- =============================================================================

-- 启用 pg_trgm 扩展（支持全文模糊搜索）
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- =============================================================================
-- 1. 用户表（xhs_users）
--    存储采集过程中发现的小红书用户信息
-- =============================================================================
CREATE TABLE IF NOT EXISTS xhs_users (
    id              SERIAL          PRIMARY KEY,
    user_id         VARCHAR(100)    UNIQUE NOT NULL,   -- 小红书用户唯一 ID（从页面/URL提取）
    username        VARCHAR(200)    NOT NULL,          -- 昵称
    profile_url     TEXT            DEFAULT '',        -- 主页链接
    bio             TEXT            DEFAULT '',        -- 个人简介
    followers_count INTEGER         DEFAULT 0,        -- 粉丝数
    following_count INTEGER         DEFAULT 0,        -- 关注数
    posts_count     INTEGER         DEFAULT 0,        -- 发帖数（采集时可见）
    is_verified     BOOLEAN         DEFAULT FALSE,     -- 是否认证账号
    first_seen_at   TIMESTAMPTZ     DEFAULT NOW(),     -- 首次发现时间
    last_updated_at TIMESTAMPTZ     DEFAULT NOW()      -- 最后更新时间
);

CREATE INDEX IF NOT EXISTS idx_users_username    ON xhs_users (username);
CREATE INDEX IF NOT EXISTS idx_users_followers   ON xhs_users (followers_count DESC);

-- =============================================================================
-- 2. 帖子表（xhs_posts）
--    存储采集到的小红书保险相关帖子
-- =============================================================================
CREATE TABLE IF NOT EXISTS xhs_posts (
    id              SERIAL          PRIMARY KEY,
    post_id         VARCHAR(150)    UNIQUE NOT NULL,   -- 小红书帖子唯一 ID（从URL提取）
    title           TEXT            DEFAULT '',        -- 帖子标题
    content         TEXT            DEFAULT '',        -- 帖子正文
    post_type       VARCHAR(20)     DEFAULT 'note',    -- 内容类型：note/video/live
    url             TEXT            DEFAULT '',        -- 帖子完整链接
    cover_image_url TEXT            DEFAULT '',        -- 封面图链接

    -- 互动数据
    likes_count     INTEGER         DEFAULT 0,         -- 点赞数
    comments_count  INTEGER         DEFAULT 0,         -- 评论数
    collects_count  INTEGER         DEFAULT 0,         -- 收藏数
    shares_count    INTEGER         DEFAULT 0,         -- 分享数

    -- 作者信息（冗余存储，方便查询）
    author_id       VARCHAR(100)    DEFAULT '',        -- 作者 user_id（关联 xhs_users）
    author_name     VARCHAR(200)    DEFAULT '',        -- 作者昵称

    -- 标签（PostgreSQL 数组类型，直接存储）
    tags            TEXT[]          DEFAULT '{}',      -- 话题标签列表（#保险# 等）

    -- 搜索关联
    search_keyword  VARCHAR(200)    DEFAULT '',        -- 发现该帖子时使用的搜索关键词

    -- 时间戳
    published_at    TIMESTAMPTZ     DEFAULT NULL,      -- 帖子发布时间（若能获取）
    collected_at    TIMESTAMPTZ     DEFAULT NOW(),     -- 爬取时间
    last_updated_at TIMESTAMPTZ     DEFAULT NOW()      -- 最后更新时间
);

CREATE INDEX IF NOT EXISTS idx_posts_author_id    ON xhs_posts (author_id);
CREATE INDEX IF NOT EXISTS idx_posts_keyword      ON xhs_posts (search_keyword);
CREATE INDEX IF NOT EXISTS idx_posts_collected_at ON xhs_posts (collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_likes        ON xhs_posts (likes_count DESC);
CREATE INDEX IF NOT EXISTS idx_posts_tags         ON xhs_posts USING GIN (tags);

-- 全文搜索索引（标题 + 正文）
CREATE INDEX IF NOT EXISTS idx_posts_fulltext
    ON xhs_posts USING GIN (to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content, '')));

-- =============================================================================
-- 3. 评论表（xhs_comments）
--    存储帖子评论（选择性采集，能采多少采多少）
-- =============================================================================
CREATE TABLE IF NOT EXISTS xhs_comments (
    id              SERIAL          PRIMARY KEY,
    comment_id      VARCHAR(150)    UNIQUE NOT NULL,   -- 评论唯一 ID
    post_id         VARCHAR(150)    NOT NULL,          -- 所属帖子 ID（关联 xhs_posts）
    author_id       VARCHAR(100)    DEFAULT '',        -- 评论者 user_id
    author_name     VARCHAR(200)    DEFAULT '',        -- 评论者昵称
    content         TEXT            NOT NULL,          -- 评论内容
    likes_count     INTEGER         DEFAULT 0,         -- 评论点赞数
    is_top_comment  BOOLEAN         DEFAULT FALSE,     -- 是否置顶评论
    published_at    TIMESTAMPTZ     DEFAULT NULL,
    collected_at    TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comments_post_id    ON xhs_comments (post_id);
CREATE INDEX IF NOT EXISTS idx_comments_author_id  ON xhs_comments (author_id);
CREATE INDEX IF NOT EXISTS idx_comments_likes      ON xhs_comments (likes_count DESC);

-- =============================================================================
-- 4. 搜索会话表（xhs_search_sessions）
--    记录每次爬虫运行的元信息，便于追踪和复查
-- =============================================================================
CREATE TABLE IF NOT EXISTS xhs_search_sessions (
    id              SERIAL          PRIMARY KEY,
    session_id      UUID            DEFAULT gen_random_uuid(),  -- 会话唯一 ID
    search_keyword  VARCHAR(200)    NOT NULL,          -- 搜索关键词
    posts_found     INTEGER         DEFAULT 0,         -- 本次找到的帖子数
    users_found     INTEGER         DEFAULT 0,         -- 本次发现的用户数
    comments_found  INTEGER         DEFAULT 0,         -- 本次采集的评论数
    status          VARCHAR(20)     DEFAULT 'running', -- running / completed / failed
    notes           TEXT            DEFAULT '',        -- 备注（如遇到的问题）
    started_at      TIMESTAMPTZ     DEFAULT NOW(),
    finished_at     TIMESTAMPTZ     DEFAULT NULL
);

-- =============================================================================
-- 5. 知识库文档表（kb_documents）
--    管理向量库中对应的文档信息、概述以及重命名
-- =============================================================================
CREATE TABLE IF NOT EXISTS kb_documents (
    id              SERIAL          PRIMARY KEY,
    collection_name VARCHAR(100)    NOT NULL,
    filename        VARCHAR(255)    NOT NULL,
    display_name    VARCHAR(255)    NOT NULL,
    summary         TEXT            DEFAULT '',
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE(collection_name, filename)
);

CREATE INDEX IF NOT EXISTS idx_kb_docs_collection ON kb_documents (collection_name);

-- =============================================================================
-- 6. 辅助视图：常用查询快捷方式
-- =============================================================================

-- 热门保险帖子（按互动量排序）
CREATE OR REPLACE VIEW v_top_posts AS
SELECT
    p.post_id,
    p.title,
    LEFT(p.content, 200) AS content_preview,
    p.author_name,
    p.likes_count,
    p.comments_count,
    p.collects_count,
    (p.likes_count + p.comments_count * 2 + p.collects_count * 3) AS engagement_score,
    p.tags,
    p.search_keyword,
    p.collected_at
FROM xhs_posts p
ORDER BY engagement_score DESC;

-- 活跃用户（发帖最多）
CREATE OR REPLACE VIEW v_active_users AS
SELECT
    u.user_id,
    u.username,
    u.followers_count,
    u.bio,
    u.profile_url,
    COUNT(p.id) AS post_count_in_db,
    MAX(p.collected_at) AS latest_post_collected_at
FROM xhs_users u
LEFT JOIN xhs_posts p ON p.author_id = u.user_id
GROUP BY u.id
ORDER BY post_count_in_db DESC, u.followers_count DESC;

-- 关键词分布统计
CREATE OR REPLACE VIEW v_keyword_stats AS
SELECT
    search_keyword,
    COUNT(*)                AS total_posts,
    AVG(likes_count)        AS avg_likes,
    AVG(comments_count)     AS avg_comments,
    MAX(collected_at)       AS last_collected
FROM xhs_posts
GROUP BY search_keyword
ORDER BY total_posts DESC;

-- =============================================================================
-- 初始化完成提示
-- =============================================================================
DO $$
BEGIN
    RAISE NOTICE '小红书数据库初始化完成：xhs_posts / xhs_users / xhs_comments / xhs_search_sessions';
END $$;
