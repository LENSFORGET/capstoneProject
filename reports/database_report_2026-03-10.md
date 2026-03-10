# 多平台潜客采集数据库报告

生成时间: 2026-03-10 14:18:23

---

## 一、social_* 多平台原始数据

| 平台 | posts | comments | users | leads |
|------|------:|--------:|------:|------:|
| bilibili | 1 | 1 | 1 | 1 |
| douyin | 1 | 1 | 1 | 1 |
| reddit | 1 | 1 | 1 | 1 |
| tieba | 1 | 1 | 1 | 1 |
| twitter | 1 | 1 | 1 | 1 |
| weibo | 1 | 1 | 1 | 1 |
| zhihu | 1 | 1 | 1 | 1 |

## 二、social_search_sessions 会话汇总

| 平台 | 会话数 | posts_found | users_found | comments_found | leads_found |
|------|------:|------------:|------------:|---------------:|------------:|
| bilibili | 1 | 1 | 1 | 1 | 1 |
| douyin | 4 | 1 | 1 | 1 | 1 |
| instagram | 3 | 0 | 0 | 0 | 0 |
| linkedin | 2 | 0 | 0 | 0 | 0 |
| reddit | 1 | 1 | 1 | 1 | 1 |
| tieba | 2 | 1 | 1 | 1 | 1 |
| twitter | 2 | 1 | 1 | 1 | 1 |
| weibo | 3 | 1 | 1 | 1 | 1 |
| zhihu | 1 | 1 | 1 | 1 | 1 |

## 三、xhs_* 小红书数据（保留）

| 表 | 数量 |
|----|------:|
| xhs_posts | 149 |
| xhs_users | 89 |
| xhs_comments | 6 |
| leads (xhs) | 0 |

## 四、leads 总表（跨平台）

| 平台 | 数量 | 平均评分 |
|------|------:|--------:|
| bilibili | 1 | 3.00 |
| douyin | 1 | 3.00 |
| reddit | 1 | 4.00 |
| tieba | 1 | 3.00 |
| twitter | 1 | 4.00 |
| weibo | 1 | 3.00 |
| zhihu | 1 | 4.00 |

## 五、结论与说明

- **多平台 social_* 表已落地**：7 个平台（bilibili、douyin、reddit、tieba、twitter、weibo、zhihu）均有 posts/comments/users/leads 记录。
- **当前有效采集数据**：主要来自 smoke 测试写入（各平台 1 条基线），非真实采集。
- **Instagram / LinkedIn**：有会话记录（3 次、2 次），但 posts_found/users_found 均为 0，说明采集因登录态或反爬未成功入库。
- **小红书数据**：xhs_posts 149 条、xhs_users 89 条、xhs_comments 6 条，为历史采集；leads 表中无 xhs 平台记录（可能未做 lead 评分或平台字段为 null）。
