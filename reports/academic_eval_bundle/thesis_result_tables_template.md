# 论文结果表模板（RAG + Agent）

## Table 1. 主结果对比（test set）
| Model/Variant | Recall@5 | nDCG@5 | Faithfulness | AnswerRelevancy | HallucinationRate↓ | AgentSuccess | ToolAccuracy | OverallScore | 95% CI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| B0 (Baseline) |  |  |  |  |  |  |  |  |  |
| A1 (no rerank) |  |  |  |  |  |  |  |  |  |
| A2 (no category filter) |  |  |  |  |  |  |  |  |  |
| A3 (topk=3) |  |  |  |  |  |  |  |  |  |
| A4 (no recovery) |  |  |  |  |  |  |  |  |  |

## Table 2. 显著性检验（相对 B0）
| Variant | Metric | Delta | p-value | Effect Size (d) | Significant (p<0.05) |
|---|---|---:|---:|---:|---|
| A1 | OverallScore |  |  |  |  |
| A2 | OverallScore |  |  |  |  |
| A3 | OverallScore |  |  |  |  |
| A4 | OverallScore |  |  |  |  |
