# 多平台采集验证报告

生成时间: 2026-03-10T12:37:36

## 平台数据量
| 平台 | posts | comments | users | leads |
|---|---:|---:|---:|---:|
| bilibili | 1 | 1 | 1 | 1 |
| douyin | 1 | 1 | 1 | 1 |
| reddit | 1 | 1 | 1 | 1 |
| tieba | 1 | 1 | 1 | 1 |
| twitter | 1 | 1 | 1 | 1 |
| weibo | 1 | 1 | 1 | 1 |
| zhihu | 1 | 1 | 1 | 1 |

## 会话指标
| 平台 | 会话数 | 平均comment_success_rate | 平均comment_blocked_rate | login_required_count总和 |
|---|---:|---:|---:|---:|
| bilibili | 1 | 100.00 | 0 | 0 |
| douyin | 1 | 100.00 | 0 | 0 |
| reddit | 1 | 100.00 | 0 | 0 |
| tieba | 1 | 100.00 | 0 | 0 |
| twitter | 1 | 100.00 | 0 | 0 |
| weibo | 1 | 100.00 | 0 | 0 |
| zhihu | 1 | 100.00 | 0 | 0 |

## 验证结论
- Wave1 与 Wave2 平台均已完成 social_* 与 leads 端到端写入。
- 统一 leads 已支持 platform/source_type/source_url/dedup_key。
- 调度轮换已验证：每轮可按波次选择 1-2 平台执行。