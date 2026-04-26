# Error Analysis Template (RAG + Agent)

## 1. Failure Type Taxonomy
| ErrorCode | Category | Definition | Typical Symptoms |
|---|---|---|---|
| E1 | RetrievalMiss | Key evidence not retrieved | Generalized answer, missing key terms |
| E2 | RetrievalRank | Evidence retrieved but ranked low | Answer cites weakly relevant snippets |
| E3 | Hallucination | Answer includes facts outside evidence | Numbers/assertions not in terms |
| E4 | ToolMisuse | Incorrect tool or parameter selection | Calling irrelevant tools, missing parameters |
| E5 | Looping | Trajectory repeats without progress | Consecutive identical actions |
| E6 | RecoveryFail | Failed to recover after exception | Fails directly after timeout |
| E7 | UnsafeAnswer | Gave advice when it should have refused | Incorrect advice in high-risk scenario |

## 2. Case Record Table
| item_id | variant | error_code | observed_output | root_cause | fix_hypothesis | priority |
|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |