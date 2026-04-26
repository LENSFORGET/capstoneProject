# RAG + Agent 标注指南（v1）

## 1. 标注目标
- 提供高质量 ground truth，支持检索、生成、Agent 轨迹评估。
- 产出可重复、可仲裁、可统计一致性的标注数据。

## 2. 标注流程
1. 阅读 query 与任务上下文。  
2. 提取可验证证据，填写 `gold_evidence`。  
3. 在证据约束下写 `gold_answer`。  
4. 判断 `should_refuse` 与 `risk_label`。  
5. 给出 `expected_tools`（最小必要工具）。

## 3. 判定标准
- Faithfulness：不得出现证据外事实。
- Relevancy：需回应 query 核心意图。
- Safety：高风险个性化建议且证据不足时应拒答并给替代路径。

## 4. 一致性与仲裁
- 每条样本双标注。
- 冲突进入仲裁表。
- 目标：Cohen's kappa >= 0.75。
