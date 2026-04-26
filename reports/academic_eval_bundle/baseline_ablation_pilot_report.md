# Baseline and Ablation Statistics Results (Pilot)

## 1. Description
- This is a `pilot` run for methodology validation.
- Purpose: Validate the "baseline-ablation-significance" pipeline is executable, not intended as the final thesis conclusion.

## 2. Execution Command
- `python reports/academic_eval_bundle/run_baseline_ablation_stats.py`

## 3. Output Files
- `significance_tests.csv`
- `run_metadata.json`

## 4. Key Results (metric: overall_score)
| variant | mean | 95% CI | delta vs B0 | p-value | significant |
|---|---:|---|---:|---:|---|
| B0 | 0.8123 | [0.8067, 0.8210] | 0.0000 | - | - |
| A1_no_rerank | 0.7757 | [0.7717, 0.7810] | -0.0367 | 0.2426 | no |
| A2_no_category_filter | 0.7517 | [0.7487, 0.7550] | -0.0607 | 0.2426 | no |
| A3_topk3 | 0.7450 | [0.7420, 0.7480] | -0.0673 | 0.2426 | no |
| A4_no_recovery | 0.7737 | [0.7707, 0.7770] | -0.0387 | 0.2426 | no |

## 5. Interpretation
- In this pilot, all ablation configurations have lower means than the baseline B0, supporting the trend that "key components are effective".
- However, with only 3 seeds per group, statistical power is insufficient, and `p-value` does not reach the significance threshold.
- To form the main thesis conclusion, sample size and run iterations need to be expanded.