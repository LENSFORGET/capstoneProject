-- =============================================================================
-- Multi-platform migration for existing xhs_data database
-- Safe to run repeatedly.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;

ALTER TABLE IF EXISTS leads
    ADD COLUMN IF NOT EXISTS platform VARCHAR(32) NOT NULL DEFAULT 'xhs',
    ADD COLUMN IF NOT EXISTS source_type VARCHAR(32) NOT NULL DEFAULT 'post_comment',
    ADD COLUMN IF NOT EXISTS source_url TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS dedup_key VARCHAR(255) NOT NULL DEFAULT '';

UPDATE leads
SET platform = 'xhs'
WHERE platform IS NULL OR platform = '';

DROP INDEX IF EXISTS idx_leads_user_post;
CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_platform_user_post
    ON leads (platform, user_id, source_post_id);
CREATE INDEX IF NOT EXISTS idx_leads_platform ON leads (platform, discovered_at DESC);

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
