# capstoneProject Academic Evaluation Protocol v1 (RAG + Agent)

## 1. Purpose and Scope
- Purpose: Upgrade project evaluation from a demonstrative score to a reproducible, statistically testable academic evaluation.
- Scope: Covers only the `RAG` and `Agent` main pipelines; UI and data pipeline overall evaluations are excluded.
- Evaluation Unit: Scored per `query/task`, then macro-averaged with confidence intervals.

## 2. Research Questions (RQ)
- RQ1: Does the current main system achieve publishable stable performance across retrieval, generation, and tool calling?
- RQ2: Do key component changes (retriever, prompts, recovery strategies) produce statistically significant performance differences?
- RQ3: Do offline evaluation metrics show consistent trends with task completion rates and risk error rates?

## 3. Dataset Definition and Splits
- Data fields: See `benchmark_schema.md` and `rag_agent_benchmark_seed_v1.jsonl`
- Split strategy (fixed random seed `20260424`):
  - train: 60%
  - dev: 20%
  - test: 20%
- Stratification dimensions:
  - RAG query types: `factoid`, `multi_hop`, `policy_explain`, `refusal_required`
  - Agent task types: `single_tool`, `multi_tool`, `recovery_required`

## 4. Metric System (Primary + Secondary)
- RAG Retrieval: `Recall@k`, `Precision@k`, `nDCG@k`, `MRR`
- RAG Generation: `Faithfulness`, `AnswerRelevancy`, `HallucinationRate`
- Agent Trajectory: `TaskSuccessRate`, `ToolCallAccuracy`, `RecoverySuccessRate`, `StepEfficiency`, `TimeoutRate`

## 5. Statistics and Significance Rules
- All core metrics report: mean, standard deviation, 95% CI.
- Confidence intervals: bootstrap (`B=1000` resamples).
- Inter-group comparison: Paired tests preferred; non-parametric tests when necessary.
- Significance threshold: `p < 0.05`.

## 6. Reproducibility Freeze Items
- Fixed model versions, prompt versions, data splits, script versions, and random seeds.
- Recommended seeds: `20260424, 20260425, 20260426`.

## 7. Baseline and Ablation Settings
- B0: Current main configuration
- A1: Remove rerank
- A2: Remove category filter
- A3: Reduce context window
- A4: Disable recovery strategy

## 8. Agreement and Disclosure
- Dual annotation + conflict adjudication, reporting Cohen's kappa (target >= 0.75).
- Pilot results are only for pipeline validation and not as final thesis conclusions.