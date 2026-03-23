"""
agent_router_mcp.py
-------------------
多 Agent 路由 MCP 工具服务。
提供工具让 Orchestrator Agent 通过 HTTP 调用各专业保险 Agent。

各专业 Agent 通过 nat serve 暴露 OpenAI-compatible Chat Completions API，
本服务直接调用其 /chat/completions 端点并返回结果给 Orchestrator。

运行方式（由 workflow_orchestrator.yaml 的 mcp_client 管理）：
    python agent_router_mcp.py

依赖环境变量：
    NAT_AGENT_LIFE_URL     - 寿险 Agent URL（默认 http://nat-agent-life:8101）
    NAT_AGENT_SAVINGS_URL  - 储蓄险 Agent URL（默认 http://nat-agent-savings:8102）
    NAT_AGENT_MEDICAL_URL  - 医疗险 Agent URL（默认 http://nat-agent-medical:8103）
    NAT_AGENT_CRITICAL_URL - 危疾险 Agent URL（默认 http://nat-agent-critical:8104）
"""

import json
import logging
import os

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

mcp = FastMCP("Insurance Agent Router")

AGENT_URLS = {
    "life": os.environ.get("NAT_AGENT_LIFE_URL", "http://nat-agent-life:8101"),
    "savings": os.environ.get("NAT_AGENT_SAVINGS_URL", "http://nat-agent-savings:8102"),
    "medical": os.environ.get("NAT_AGENT_MEDICAL_URL", "http://nat-agent-medical:8103"),
    "critical": os.environ.get("NAT_AGENT_CRITICAL_URL", "http://nat-agent-critical:8104"),
}

TIMEOUT = 120.0


async def _call_agent(agent_key: str, query: str) -> str:
    """向指定专业 Agent 发送问题并返回回答。"""
    url = AGENT_URLS[agent_key]
    endpoint = f"{url}/chat/completions/stream"

    logger.info("调用 %s Agent: %s -> %s", agent_key, query[:50], url)

    payload = {
        "messages": [{"role": "user", "content": query}],
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # 先尝试流式端点，失败则用非流式
            try:
                response = await client.post(
                    f"{url}/chat/completions",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()

                # 提取回答内容
                if "choices" in data:
                    content = data["choices"][0].get("message", {}).get("content", "")
                    if content:
                        return content

                return str(data)

            except httpx.HTTPStatusError as e:
                logger.warning("Chat completions 失败(%s)，尝试 generate: %s", e.response.status_code, e)
                # 尝试 generate 端点
                gen_response = await client.post(
                    f"{url}/generate",
                    json={"input": query},
                    headers={"Content-Type": "application/json"},
                )
                gen_response.raise_for_status()
                gen_data = gen_response.json()
                return str(gen_data.get("output", gen_data))

    except httpx.TimeoutException:
        return f"[{agent_key} Agent 超时] 请稍后重试。Agent 可能仍在初始化中（连接 Milvus 和加载模型可能需要约 30 秒）。"
    except httpx.ConnectError as e:
        return f"[{agent_key} Agent 连接失败] 服务可能未完全启动，请稍候：{e}"
    except Exception as e:
        logger.error("调用 %s Agent 出错: %s", agent_key, e, exc_info=True)
        return f"[{agent_key} Agent 错误] {e}"


@mcp.tool()
async def ask_life_agent(query: str) -> str:
    """
    向寿险专业顾问咨询。
    适用问题：定期寿险、万能寿险、终身寿险、身故保障、遗产规划等。
    涵盖产品：ManuTerm、Universal Life、La Vie 2、ManuCentury。

    Args:
        query: 用户关于寿险的具体问题
    """
    return await _call_agent("life", query)


@mcp.tool()
async def ask_savings_agent(query: str) -> str:
    """
    向储蓄与年金险专业顾问咨询。
    适用问题：储蓄保险、退休年金、教育基金、财富增值、QDAP 税务扣减等。
    涵盖产品：FlexiFortune、Genesis 系列、Harvest Saver、Prestige 系列、ManuLeisure 年金、Future Assure。

    Args:
        query: 用户关于储蓄或年金险的具体问题
    """
    return await _call_agent("savings", query)


@mcp.tool()
async def ask_medical_agent(query: str) -> str:
    """
    向医疗险与 VHIS 专业顾问咨询。
    适用问题：住院医疗险、VHIS 自愿医保、手术费用报销、门诊、税务扣减（医疗类）等。
    涵盖产品：VHIS 灵活计划、VHIS 标准计划、Supreme 高端医疗。

    Args:
        query: 用户关于医疗险或 VHIS 的具体问题
    """
    return await _call_agent("medical", query)


@mcp.tool()
async def ask_critical_agent(query: str) -> str:
    """
    向危疾与综合保障专业顾问咨询。
    适用问题：危疾险、重疾险、癌症保障、心脏病、脑中风、失能保障等。
    涵盖产品：ManuPremier Protector、Whole-in-One Prime 3、ManuDelight HK。

    Args:
        query: 用户关于危疾险或综合保障的具体问题
    """
    return await _call_agent("critical", query)


@mcp.tool()
def list_agents() -> str:
    """
    列出所有可用的专业保险顾问 Agent 及其负责领域。
    用于了解各 Agent 的分工和联系方式。
    """
    lines = ["宏利保险专业顾问团队：\n"]
    agent_info = {
        "life": ("寿险专业顾问", "ManuTerm、Universal Life、La Vie 2、ManuCentury"),
        "savings": ("储蓄与年金险顾问", "FlexiFortune、Genesis 系列、Harvest Saver、Prestige 系列、ManuLeisure 年金"),
        "medical": ("医疗险与 VHIS 顾问", "VHIS 灵活/标准/Supreme 计划"),
        "critical": ("危疾与综合保障顾问", "ManuPremier Protector、Whole-in-One Prime、ManuDelight"),
    }
    for key, (name, products) in agent_info.items():
        url = AGENT_URLS[key]
        lines.append(f"• {name}（{key}）")
        lines.append(f"  产品：{products}")
        lines.append(f"  地址：{url}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
