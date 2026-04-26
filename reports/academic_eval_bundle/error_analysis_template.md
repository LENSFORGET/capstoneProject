# 误差分析模板（RAG + Agent）

## 1. 失败类型 taxonomy
| ErrorCode | 类别 | 定义 | 典型症状 |
|---|---|---|---|
| E1 | RetrievalMiss | 关键证据未被召回 | 回答泛化、缺关键条款 |
| E2 | RetrievalRank | 证据召回但排序靠后 | 回答引用弱相关片段 |
| E3 | Hallucination | 回答包含证据外事实 | 出现条款外数字/断言 |
| E4 | ToolMisuse | 工具或参数选择错误 | 调用无关工具、参数缺失 |
| E5 | Looping | 轨迹重复无进展 | 连续相同 action |
| E6 | RecoveryFail | 异常后未恢复 | 超时后直接失败 |
| E7 | UnsafeAnswer | 应拒答却给出建议 | 高风险场景错误建议 |

## 2. 个案记录表
| item_id | variant | error_code | observed_output | root_cause | fix_hypothesis | priority |
|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |
