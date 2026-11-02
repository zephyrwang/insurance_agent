"""
Shared factory for specialist agents.

Uses LangChain's native tool-calling agent construction (create_tool_calling_agent)
rather than the legacy initialize_agent / STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION
convention, which asks the model to write a JSON action blob as plain text. That
text-based convention is unreliable with reasoning models (observed with
openai/gpt-oss-120b): the model can route its actual output into a hidden
"reasoning" channel and leave the visible completion empty, which upstream code
then has nothing to work with. Native tool-calling uses the provider's structured
tool-call API instead, which these models handle correctly and deterministically.
"""

from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain.memory import ConversationBufferWindowMemory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


def build_specialist_agent(tools, system_prompt: str, llm):
    """Wire up a tool-calling agent with windowed conversation memory."""
    memory = ConversationBufferWindowMemory(memory_key="chat_history", return_messages=True, k=5)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )

    agent = create_tool_calling_agent(llm, tools, prompt)

    return AgentExecutor(
        agent=agent,
        tools=tools,
        memory=memory,
        verbose=True,
        handle_parsing_errors=True,
    )
