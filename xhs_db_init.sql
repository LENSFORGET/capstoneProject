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
-- 5. 潜在客户线索表（leads）
--    由 AI 助理识别、评分，供保险代理人跟进
-- =============================================================================
CREATE TABLE IF NOT EXISTS leads (
    id              SERIAL          PRIMARY KEY,
    user_id         VARCHAR(100)    NOT NULL,              -- 小红书用户 ID
    username        VARCHAR(200)    DEFAULT '',             -- 用户昵称
    profile_url     TEXT            DEFAULT '',             -- 主页链接
    lead_score      SMALLINT        DEFAULT 1 CHECK (lead_score BETWEEN 1 AND 5), -- 意向评分 1-5
    lead_reason     TEXT            DEFAULT '',             -- 识别原因（AI 判断依据）
    contact_hint    TEXT            DEFAULT '',             -- 联系线索（如"评论求推荐顾问"）
    source_post_id  VARCHAR(150)    DEFAULT '',             -- 来源帖子 ID
    source_keyword  VARCHAR(200)    DEFAULT '',             -- 触发的搜索关键词
    insurance_interest TEXT[]       DEFAULT '{}',          -- 感兴趣的险种（如 重疾险、医疗险）
    status          VARCHAR(20)     DEFAULT 'new',          -- new / reviewed / contacted / closed
    notes           TEXT            DEFAULT '',             -- 人工备注（代理人填写）
    discovered_at   TIMESTAMPTZ     DEFAULT NOW(),          -- 首次发现时间
    last_updated_at TIMESTAMPTZ     DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_user_post ON leads (user_id, source_post_id);
CREATE INDEX IF NOT EXISTS idx_leads_score      ON leads (lead_score DESC);
CREATE INDEX IF NOT EXISTS idx_leads_status     ON leads (status);
CREATE INDEX IF NOT EXISTS idx_leads_keyword    ON leads (source_keyword);
CREATE INDEX IF NOT EXISTS idx_leads_discovered ON leads (discovered_at DESC);

-- 多平台扩展字段（兼容旧库，默认保留 XHS 行为）
ALTER TABLE IF EXISTS leads
    ADD COLUMN IF NOT EXISTS platform VARCHAR(32) NOT NULL DEFAULT 'xhs',
    ADD COLUMN IF NOT EXISTS source_type VARCHAR(32) NOT NULL DEFAULT 'post_comment',
    ADD COLUMN IF NOT EXISTS source_url TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS dedup_key VARCHAR(255) NOT NULL DEFAULT '';

UPDATE leads
SET platform = 'xhs'
WHERE platform IS NULL OR platform = '';

-- 迁移到跨平台唯一性：platform + user_id + source_post_id
DROP INDEX IF EXISTS idx_leads_user_post;
CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_platform_user_post
    ON leads (platform, user_id, source_post_id);
CREATE INDEX IF NOT EXISTS idx_leads_platform ON leads (platform, discovered_at DESC);

-- =============================================================================
-- 6. 点赞记录表（liked_posts）
--    记录 AI 已点赞的帖子，避免重复点赞
-- =============================================================================
CREATE TABLE IF NOT EXISTS liked_posts (
    id              SERIAL          PRIMARY KEY,
    post_id         VARCHAR(150)    UNIQUE NOT NULL,        -- 已点赞的帖子 ID
    post_url        TEXT            DEFAULT '',             -- 帖子链接
    post_title      TEXT            DEFAULT '',             -- 帖子标题（冗余记录）
    liked_reason    TEXT            DEFAULT '',             -- 点赞原因（高质量内容等）
    liked_at        TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_liked_posts_at ON liked_posts (liked_at DESC);

-- =============================================================================
-- 7. 知识库文档表（kb_documents）
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
-- 9. 多平台原始数据表（social_*）
-- =============================================================================

CREATE TABLE IF NOT EXISTS social_users (
    id              SERIAL          PRIMARY KEY,
    platform        VARCHAR(32)     NOT NULL,
    user_id         VARCHAR(150)    NOT NULL,
    username        VARCHAR(255)    NOT NULL,
    profile_url     TEXT            DEFAULT '',
    bio             TEXT            DEFAULT '',
    followers_count INTEGER         DEFAULT 0,
    following_count INTEGER         DEFAULT 0,
    posts_count     INTEGER         DEFAULT 0,
    is_verified     BOOLEAN         DEFAULT FALSE,
    extra           JSONB           DEFAULT '{}'::jsonb,
    first_seen_at   TIMESTAMPTZ     DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE(platform, user_id)
);

CREATE INDEX IF NOT EXISTS idx_social_users_platform ON social_users (platform, followers_count DESC);
CREATE INDEX IF NOT EXISTS idx_social_users_name ON social_users (username);

CREATE TABLE IF NOT EXISTS social_posts (
    id              SERIAL          PRIMARY KEY,
    platform        VARCHAR(32)     NOT NULL,
    post_id         VARCHAR(200)    NOT NULL,
    title           TEXT            DEFAULT '',
    content         TEXT            DEFAULT '',
    url             TEXT            DEFAULT '',
    post_type       VARCHAR(32)     DEFAULT 'post',
    cover_image_url TEXT            DEFAULT '',
    likes_count     INTEGER         DEFAULT 0,
    comments_count  INTEGER         DEFAULT 0,
    collects_count  INTEGER         DEFAULT 0,
    shares_count    INTEGER         DEFAULT 0,
    author_id       VARCHAR(150)    DEFAULT '',
    author_name     VARCHAR(255)    DEFAULT '',
    tags            TEXT[]          DEFAULT '{}',
    search_keyword  VARCHAR(255)    DEFAULT '',
    published_at    TIMESTAMPTZ     DEFAULT NULL,
    collected_at    TIMESTAMPTZ     DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ     DEFAULT NOW(),
    extra           JSONB           DEFAULT '{}'::jsonb,
    UNIQUE(platform, post_id)
);

CREATE INDEX IF NOT EXISTS idx_social_posts_platform ON social_posts (platform, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_social_posts_author ON social_posts (platform, author_id);
CREATE INDEX IF NOT EXISTS idx_social_posts_keyword ON social_posts (platform, search_keyword);
CREATE INDEX IF NOT EXISTS idx_social_posts_tags ON social_posts USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_social_posts_fulltext
    ON social_posts USING GIN (to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content, '')));

CREATE TABLE IF NOT EXISTS social_comments (
    id              SERIAL          PRIMARY KEY,
    platform        VARCHAR(32)     NOT NULL,
    comment_id      VARCHAR(200)    NOT NULL,
    post_id         VARCHAR(200)    NOT NULL,
    author_id       VARCHAR(150)    DEFAULT '',
    author_name     VARCHAR(255)    DEFAULT '',
    content         TEXT            NOT NULL,
    likes_count     INTEGER         DEFAULT 0,
    is_top_comment  BOOLEAN         DEFAULT FALSE,
    source_type     VARCHAR(32)     DEFAULT 'comment',
    published_at    TIMESTAMPTZ     DEFAULT NULL,
    collected_at    TIMESTAMPTZ     DEFAULT NOW(),
    extra           JSONB           DEFAULT '{}'::jsonb,
    UNIQUE(platform, comment_id)
);

CREATE INDEX IF NOT EXISTS idx_social_comments_platform_post
    ON social_comments (platform, post_id, likes_count DESC);
CREATE INDEX IF NOT EXISTS idx_social_comments_author ON social_comments (platform, author_id);

CREATE TABLE IF NOT EXISTS social_search_sessions (
    id                   SERIAL          PRIMARY KEY,
    session_id           UUID            DEFAULT gen_random_uuid(),
    platform             VARCHAR(32)     NOT NULL,
    search_keyword       VARCHAR(255)    NOT NULL,
    posts_found          INTEGER         DEFAULT 0,
    users_found          INTEGER         DEFAULT 0,
    comments_found       INTEGER         DEFAULT 0,
    leads_found          INTEGER         DEFAULT 0,
    comment_success_rate NUMERIC(6,2)    DEFAULT 0,
    comment_blocked_rate NUMERIC(6,2)    DEFAULT 0,
    login_required_count INTEGER         DEFAULT 0,
    status               VARCHAR(20)     DEFAULT 'running',
    notes                TEXT            DEFAULT '',
    started_at           TIMESTAMPTZ     DEFAULT NOW(),
    finished_at          TIMESTAMPTZ     DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_social_sessions_platform
    ON social_search_sessions (platform, started_at DESC);

-- =============================================================================
-- 8. 辅助视图：常用查询快捷方式
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

-- 高意向潜在客户视图（评分 >= 4）
CREATE OR REPLACE VIEW v_hot_leads AS
SELECT
    l.user_id,
    l.username,
    l.lead_score,
    l.lead_reason,
    l.contact_hint,
    l.insurance_interest,
    l.source_keyword,
    p.title         AS source_post_title,
    p.url           AS source_post_url,
    l.status,
    l.discovered_at
FROM leads l
LEFT JOIN xhs_posts p ON p.post_id = l.source_post_id
WHERE l.lead_score >= 4
ORDER BY l.lead_score DESC, l.discovered_at DESC;

-- =============================================================================
-- 初始化完成提示
-- =============================================================================
DO $$
BEGIN
    RAISE NOTICE '数据库初始化完成：xhs_* + leads + liked_posts + social_* 多平台表';
END $$;
