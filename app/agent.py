from botocore.config import Config
from gen_ai_hub.proxy import GenAIHubProxyClient, set_proxy_version
from gen_ai_hub.proxy.langchain.amazon import ChatBedrockConverse
from langgraph.prebuilt import create_react_agent
import os

from .tools import ALL_TOOLS

SYSTEM_PROMPT = """..."""  # keep your full prompt


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