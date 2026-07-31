"""
Shared factory for specialist agents.

All three specialists are STRUCTURED_CHAT agents so tools can take multiple
typed arguments (Pydantic args_schema on each StructuredTool) instead of a
single free-text string the tool has to regex-parse.
"""

from langchain.agents import initialize_agent, AgentType
from langchain.memory import ConversationBufferWindowMemory
from langchain.prompts import MessagesPlaceholder


def build_specialist_agent(tools, system_prompt: str, llm):
    """Wire up a structured-chat ReAct agent with windowed conversation memory."""
    memory = ConversationBufferWindowMemory(memory_key="chat_history", return_messages=True, k=5)

    return initialize_agent(
        tools=tools,
        llm=llm,
        agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
        memory=memory,
        verbose=True,
        agent_kwargs={
            "prefix": system_prompt + "\n\nYou have access to the following tools:",
            "memory_prompts": [MessagesPlaceholder(variable_name="chat_history")],
            "input_variables": ["input", "agent_scratchpad", "chat_history"],
        },
        handle_parsing_errors=True,
    )
