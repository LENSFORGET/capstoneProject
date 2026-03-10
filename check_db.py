import psycopg2
import os

conn = psycopg2.connect(
    host='localhost',
    port=int(os.getenv('POSTGRES_PORT', 15432)),
    dbname='xhs_data',
    user='xhs_user',
    password=os.getenv('POSTGRES_PASSWORD', 'xhs_secure_pass')
)
cur = conn.cursor()

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='xhs_posts' ORDER BY ordinal_position")
print('xhs_posts 字段:', [r[0] for r in cur.fetchall()])

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='xhs_comments' ORDER BY ordinal_position")
print('xhs_comments 字段:', [r[0] for r in cur.fetchall()])

print()
print('=== 帖子列表 ===')
cur.execute('SELECT post_id, title, author_name, likes_count, comments_count, tags FROM xhs_posts')
rows = cur.fetchall()
if rows:
    for row in rows:
        print(f'ID: {row[0]} | 作者: {row[2]} | 点赞: {row[3]} | 评论: {row[4]}')
        print(f'标题: {row[1]}')
        print(f'标签: {row[5]}')
        print('---')
else:
    print('无帖子数据')

print()
print('=== 评论列表 ===')
cur.execute('SELECT comment_id, post_id, content, author_name, likes_count FROM xhs_comments')
rows = cur.fetchall()
if rows:
    for row in rows:
        content_preview = (row[2] or '')[:80]
        print(f'[{row[0]}] post:{row[1]} | 作者:{row[3]} | 点赞:{row[4]}')
        print(f'内容: {content_preview}')
        print('---')
else:
    print('无评论数据')

print()
print('=== 会话列表 ===')
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='xhs_search_sessions' ORDER BY ordinal_position")
cols = [r[0] for r in cur.fetchall()]
print('xhs_search_sessions 字段:', cols)

cur.execute('SELECT * FROM xhs_search_sessions')
rows = cur.fetchall()
for row in rows:
    print(dict(zip(cols, row)))

cur.close()
conn.close()
print()
print('验证完成！')
