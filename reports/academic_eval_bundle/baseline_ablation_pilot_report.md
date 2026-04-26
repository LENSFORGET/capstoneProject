# Baseline 与消融统计结果（Pilot）

## 1. 说明
- 本次为方法验证性质的 `pilot` 运行。
- 目的：验证“基线-消融-显著性”流程可执行，不作为最终论文主结果。

## 2. 执行命令
- `python reports/academic_eval_bundle/run_baseline_ablation_stats.py`

## 3. 输出文件
- `significance_tests.csv`
- `run_metadata.json`

## 4. 关键结果（metric: overall_score）
| variant | mean | 95% CI | delta vs B0 | p-value | significant |
|---|---:|---|---:|---:|---|
| B0 | 0.8123 | [0.8067, 0.8210] | 0.0000 | - | - |
| A1_no_rerank | 0.7757 | [0.7717, 0.7810] | -0.0367 | 0.2426 | no |
| A2_no_category_filter | 0.7517 | [0.7487, 0.7550] | -0.0607 | 0.2426 | no |
| A3_topk3 | 0.7450 | [0.7420, 0.7480] | -0.0673 | 0.2426 | no |
| A4_no_recovery | 0.7737 | [0.7707, 0.7770] | -0.0387 | 0.2426 | no |

## 5. 解释
- 该 pilot 中所有消融配置均值都低于基线 B0，趋势上支持“关键组件有效”。
- 但每组仅 3 个 seed，统计功效不足，`p-value` 未达到显著性阈值。
- 要形成论文主结论，需要扩大样本量和运行次数。
