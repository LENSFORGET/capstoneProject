# Academic RAG+Agent Evaluation Overview (Single Directory Version)

## Purpose
- Consolidate evaluation assets into a single directory for easy analysis and thesis writing.
- This directory covers protocols, data, scripts, results, thesis templates, and defense talking points.

## Methodology Summary
- RAG Retrieval: Recall@k, Precision@k, nDCG@k, MRR
- RAG Generation: Faithfulness, AnswerRelevancy, HallucinationRate
- Agent Trajectory: TaskSuccess, ToolCallAccuracy, RecoverySuccess, TimeoutRate
- Statistics: bootstrap 95% CI + significance testing

## Key Files
- Protocol: `eval_protocol_rag_agent_v1.md`
- Data: `benchmark_schema.md`, `annotation_guideline.md`, `rag_agent_benchmark_seed_v1.jsonl`
- Agreement: `dual_annotations_sample.csv`, `compute_annotation_agreement.py`, `annotation_agreement_report.md`
- Experiments: `baseline_ablation_runs_pilot.csv`, `run_baseline_ablation_stats.py`, `significance_tests.csv`, `run_metadata.json`
- Thesis Templates: `thesis_result_tables_template.md`, `error_analysis_template.md`
- Defense Talking Points: `defense_talking_points.md`

## Verified Conclusions (Pilot)
- should_refuse kappa = 1.0000
- risk_label kappa = 0.9222
- B0 overall_score mean = 0.8123, CI95 [0.8067, 0.8210]
- Ablation means are lower than baseline, but lack significance at the current sample size.

## Notes
- Pilot results are only for pipeline validation and should not be used as final thesis conclusions.
- The formal thesis requires rerunning with an expanded test sample and more seeds.