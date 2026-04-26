# 标注一致性报告（seed_v1 样本）

## 数据来源
- 标注文件：`dual_annotations_sample.csv`
- 统计脚本：`compute_annotation_agreement.py`

## 结果
- `should_refuse` Cohen's kappa = `1.0000`
- `risk_label` Cohen's kappa = `0.9222`

## 解释
- 两个维度都高于常见学术门槛 `0.75`，seed 样本一致性可接受。
- 正式论文阶段需在完整评测集上重新报告。
