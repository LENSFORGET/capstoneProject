# RAG + Agent Evaluation Set Field Schema (v1)

## 1. File Format
- Main data file: `rag_agent_benchmark_seed_v1.jsonl`
- One JSON object per line (UTF-8 encoded).

## 2. Field Definitions
| Field Name | Type | Required | Description |
|---|---|---|---|
| item_id | string | Yes | Unique sample ID, e.g., `RAG-001` |
| split | string | Yes | `train/dev/test` |
| language | string | Yes | `zh-Hans` |
| query | string | Yes | User question or task instruction |
| query_type | string | Yes | `factoid/multi_hop/policy_explain/refusal_required` |
| task_type | string | Yes | `single_tool/multi_tool/recovery_required` |
| difficulty | string | Yes | `easy/medium/hard` |
| gold_answer | string | Yes | Reference answer (can be summarized) |
| gold_evidence | array[string] | Yes | List of evidence snippets or document identifiers |
| expected_tools | array[string] | Yes | Expected toolchain (e.g., `search_insurance`) |
| should_refuse | bool | Yes | Whether it should refuse to answer/transfer to human |
| risk_label | string | Yes | `low/medium/high` |
| scoring_notes | string | No | Annotation notes |