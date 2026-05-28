# ══════════════════════════════════════════════════════════════════════════
#  A2A Executor Bridge — Connects A2A protocol to LangGraph agent
# ══════════════════════════════════════════════════════════════════════════

import logging
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage

from .agent import create_agent

logger = logging.getLogger(__name__)

# Lazy-initialized agent
_agent = None


def get_agent():
    global _agent
    if _agent is None:
        _agent = create_agent()
    return _agent


async def execute_agent(user_message: str, session_id: str = "default") -> AsyncGenerator[dict, None]:
    """Execute the agent and yield A2A-compatible response events.

    Yields dicts with:
      - {"type": "message", "content": "..."}  — final text response
      - {"type": "thinking", "content": "..."}  — intermediate thoughts (optional)
    """
    try:
        agent = get_agent()

        # Run the agent
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=user_message)]},
            config={"configurable": {"thread_id": session_id}},
        )

        # Extract the final AI message
        ai_messages = [m for m in result["messages"] if m.type == "ai" and m.content]
        if ai_messages:
            final_content = ai_messages[-1].content
        else:
            final_content = "I processed your request but have no additional response."

        yield {"type": "message", "content": final_content}

    except Exception as e:
        logger.error(f"Agent execution error: {e}", exc_info=True)
        yield {"type": "message", "content": f"An error occurred: {str(e)}"}
