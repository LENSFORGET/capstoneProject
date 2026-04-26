# capstoneProject 学术评估协议 v1（RAG + Agent）

## 1. 目的与范围
- 目的：将项目评估从展示型评分升级为可复现、可统计检验的学术评估。
- 范围：仅覆盖 `RAG` 与 `Agent` 两条主链路，不纳入 UI 与数据管线总评。
- 评估单位：按 `query/task` 逐条打分，再做宏平均与置信区间。

## 2. 研究问题（Research Questions）
- RQ1：当前主系统在检索、生成、工具调用三个层面是否达到可发表的稳定性能？
- RQ2：关键组件变动（检索器、提示词、恢复策略）是否产生统计显著的性能差异？
- RQ3：离线评估指标是否与任务完成率、风险错误率具备一致趋势？

## 3. 数据集定义与切分
- 数据字段：见 `benchmark_schema.md` 与 `rag_agent_benchmark_seed_v1.jsonl`
- 切分策略（固定随机种子 `20260424`）：
  - train: 60%
  - dev: 20%
  - test: 20%
- 分层维度：
  - RAG 问题类型：`factoid`, `multi_hop`, `policy_explain`, `refusal_required`
  - Agent 任务类型：`single_tool`, `multi_tool`, `recovery_required`

## 4. 指标体系（主指标 + 辅指标）
- RAG 检索：`Recall@k`, `Precision@k`, `nDCG@k`, `MRR`
- RAG 生成：`Faithfulness`, `AnswerRelevancy`, `HallucinationRate`
- Agent 轨迹：`TaskSuccessRate`, `ToolCallAccuracy`, `RecoverySuccessRate`, `StepEfficiency`, `TimeoutRate`

## 5. 统计与显著性规则
- 所有核心指标都报告：均值、标准差、95% CI。
- 置信区间：bootstrap（`B=1000` 重采样）。
- 组间比较：配对检验优先，必要时使用非参数检验。
- 显著性阈值：`p < 0.05`。

## 6. 可复现性冻结项
- 固定模型版本、prompt 版本、数据切分、脚本版本与随机种子。
- 推荐 seeds：`20260424, 20260425, 20260426`。

## 7. 基线与消融设置
- B0：当前主配置
- A1：去掉 rerank
- A2：去掉 category filter
- A3：缩减 context window
- A4：禁用恢复策略

## 8. 一致性与披露
- 双标注 + 冲突仲裁，报告 Cohen's kappa（目标 >= 0.75）。
- pilot 结果仅用于流程验证，不作为最终论文结论。
