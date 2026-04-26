# 学术化 RAG+Agent 评估总览（单目录版）

## 目的
- 将评估资产集中在一个目录，便于分析和论文写作。
- 本目录覆盖协议、数据、脚本、结果、论文模板与答辩口径。

## 方法摘要
- RAG 检索：Recall@k, Precision@k, nDCG@k, MRR
- RAG 生成：Faithfulness, AnswerRelevancy, HallucinationRate
- Agent 轨迹：TaskSuccess, ToolCallAccuracy, RecoverySuccess, TimeoutRate
- 统计：bootstrap 95% CI + 显著性检验

## 关键文件
- 协议：`eval_protocol_rag_agent_v1.md`
- 数据：`benchmark_schema.md`, `annotation_guideline.md`, `rag_agent_benchmark_seed_v1.jsonl`
- 一致性：`dual_annotations_sample.csv`, `compute_annotation_agreement.py`, `annotation_agreement_report.md`
- 实验：`baseline_ablation_runs_pilot.csv`, `run_baseline_ablation_stats.py`, `significance_tests.csv`, `run_metadata.json`
- 论文模板：`thesis_result_tables_template.md`, `error_analysis_template.md`
- 答辩口径：`defense_talking_points.md`

## 已验证结论（pilot）
- should_refuse kappa = 1.0000
- risk_label kappa = 0.9222
- B0 overall_score mean = 0.8123, CI95 [0.8067, 0.8210]
- 消融均值低于基线，但当前样本量下显著性不足

## 注意事项
- pilot 结果仅用于流程验证，不作为最终论文主结论。
- 正式论文需要扩大 test 样本和 seed 次数后重跑。
