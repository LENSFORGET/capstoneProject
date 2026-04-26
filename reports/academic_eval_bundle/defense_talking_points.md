# 答辩口径（学术化 RAG + Agent 评估）

- 评估不是单一分数，而是 RAG 检索、RAG 生成、Agent 轨迹三层分解。
- 指标采用学术常用集合：Recall/Precision/nDCG/MRR + Faithfulness/Relevancy/Hallucination + TaskSuccess/ToolAccuracy。
- 结果报告均值、95% CI、显著性检验，不只看平均分。
- 固定数据切分、随机种子、模型与脚本版本，保证复现性。
- pilot 仅用于流程验证，论文主结论必须来自正式 test 集真实跑分。
