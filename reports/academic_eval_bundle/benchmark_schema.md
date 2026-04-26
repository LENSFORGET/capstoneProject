# RAG + Agent 评测集字段规范（v1）

## 1. 文件格式
- 主数据文件：`rag_agent_benchmark_seed_v1.jsonl`
- 每行一个 JSON 对象（UTF-8 编码）。

## 2. 字段定义
| 字段名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| item_id | string | 是 | 样本唯一 ID，如 `RAG-001` |
| split | string | 是 | `train/dev/test` |
| language | string | 是 | `zh-Hans` |
| query | string | 是 | 用户问题或任务指令 |
| query_type | string | 是 | `factoid/multi_hop/policy_explain/refusal_required` |
| task_type | string | 是 | `single_tool/multi_tool/recovery_required` |
| difficulty | string | 是 | `easy/medium/hard` |
| gold_answer | string | 是 | 参考答案（可摘要） |
| gold_evidence | array[string] | 是 | 证据片段或文档标识列表 |
| expected_tools | array[string] | 是 | 期望工具链（如 `search_insurance`） |
| should_refuse | bool | 是 | 是否应拒答/转人工 |
| risk_label | string | 是 | `low/medium/high` |
| scoring_notes | string | 否 | 标注备注 |
