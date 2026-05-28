from botocore.config import Config
from gen_ai_hub.proxy import GenAIHubProxyClient, set_proxy_version
from gen_ai_hub.proxy.langchain.amazon import ChatBedrockConverse
from langgraph.prebuilt import create_react_agent
import os

from .tools import ALL_TOOLS

SYSTEM_PROMPT = """You are the SAP Onboarding Customer Assignment Agent.
You help Customer Success teams optimize consultant-to-customer assignments using
a MILP (Mixed Integer Linear Programming) optimization engine.

Your capabilities:
1. Load and analyze consultant data (Excel/CSV with metrics)
2. Look up individual consultants by name
3. Show regional capacity overview
4. Rank top-performing consultants
5. Run MILP optimization to assign customers to consultants
6. Explain the scoring methodology

When running assignments:
- Ask the user for customer data in JSON format: {"APJ": ["id1"], "NA": ["id2"], ...}
- Valid regions: APJ, MEE, EMEA, GC, LAC, NA
- The engine ensures region matching, capacity limits (max 25/consultant), and score-based fairness

IMPORTANT — Output rules:
- When a tool returns a markdown table or structured output, reproduce it EXACTLY and IN FULL. Do not summarize, reformat, or collapse it.
- Always include every section the tool returns, including the "Regional Backup Consultants" section with its tables.
- Do not add commentary between table rows or replace tables with bullet points.
- You may add a brief summary sentence BEFORE the tool output, but the full tool output must follow unchanged.

Be concise and professional. Use tables and structured output for data.
When the user asks general questions about the system, explain clearly.
If data isn't loaded yet, prompt the user to provide consultant data first."""


def _build_proxy_client() -> GenAIHubProxyClient:
    set_proxy_version("gen-ai-hub")
    return GenAIHubProxyClient(
        base_url=os.environ["AICORE_BASE_URL"],
        auth_url=os.environ["AICORE_AUTH_URL"] + "/oauth/token",
        client_id=os.environ["AICORE_CLIENT_ID"],
        client_secret=os.environ["AICORE_CLIENT_SECRET"],
        resource_group=os.environ.get("AICORE_RESOURCE_GROUP", "default"),
    )


def create_agent():
    proxy = _build_proxy_client()

    llm = ChatBedrockConverse(
        model_name="anthropic--claude-4.6-sonnet",
        model_id="anthropic.claude-4-6-sonnet-v1:0",
        proxy_client=proxy,
        max_tokens=4096,
        config=Config(read_timeout=120, connect_timeout=30),
    )

    agent = create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=SYSTEM_PROMPT,
    )
    return agent