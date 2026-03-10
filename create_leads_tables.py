import psycopg2
import os

conn = psycopg2.connect(
    host='localhost',
    port=int(os.getenv('POSTGRES_PORT', 15432)),
    dbname='xhs_data',
    user='xhs_user',
    password=os.getenv('POSTGRES_PASSWORD', 'xhs_secure_pass')
)
conn.autocommit = True
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS leads (
    id              SERIAL          PRIMARY KEY,
    user_id         VARCHAR(100)    NOT NULL,
    username        VARCHAR(200)    DEFAULT '',
    profile_url     TEXT            DEFAULT '',
    lead_score      SMALLINT        DEFAULT 1 CHECK (lead_score BETWEEN 1 AND 5),
    lead_reason     TEXT            DEFAULT '',
    contact_hint    TEXT            DEFAULT '',
    source_post_id  VARCHAR(150)    DEFAULT '',
    source_keyword  VARCHAR(200)    DEFAULT '',
    insurance_interest TEXT[]       DEFAULT '{}',
    status          VARCHAR(20)     DEFAULT 'new',
    notes           TEXT            DEFAULT '',
    discovered_at   TIMESTAMPTZ     DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ     DEFAULT NOW()
)
""")
print("leads 表: OK")

cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_user_post ON leads (user_id, source_post_id)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_score ON leads (lead_score DESC)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads (status)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_discovered ON leads (discovered_at DESC)")
print("leads 索引: OK")

cur.execute("""
CREATE TABLE IF NOT EXISTS liked_posts (
    id           SERIAL          PRIMARY KEY,
    post_id      VARCHAR(150)    UNIQUE NOT NULL,
    post_url     TEXT            DEFAULT '',
    post_title   TEXT            DEFAULT '',
    liked_reason TEXT            DEFAULT '',
    liked_at     TIMESTAMPTZ     DEFAULT NOW()
)
""")
print("liked_posts 表: OK")

cur.execute("CREATE INDEX IF NOT EXISTS idx_liked_posts_at ON liked_posts (liked_at DESC)")
print("liked_posts 索引: OK")

cur.execute("CREATE OR REPLACE VIEW v_hot_leads AS SELECT l.user_id, l.username, l.lead_score, l.lead_reason, l.contact_hint, l.insurance_interest, l.source_keyword, p.title AS source_post_title, p.url AS source_post_url, l.status, l.discovered_at FROM leads l LEFT JOIN xhs_posts p ON p.post_id = l.source_post_id WHERE l.lead_score >= 4 ORDER BY l.lead_score DESC, l.discovered_at DESC")
print("v_hot_leads 视图: OK")

cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
print("数据库全部表:", [r[0] for r in cur.fetchall()])

cur.close()
conn.close()
print("\n数据库变更完成！")
