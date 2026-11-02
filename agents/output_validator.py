"""
Output format validation and enforcement for specialist agent responses.

All specialist system prompts require:
  1. A markdown table for any structured data
  2. A **Comment** section with bullet insights

validate_tabular_output()  — pure string check, no LLM needed (fast, testable)
enforce_tabular_format()   — calls llm.invoke() to reformat if a table is missing
"""

import json
import re
from typing import List, Optional

# Agent names as they appear in "Please ask the X Agent" deferral phrases
# (see each agent's SYSTEM_PROMPT), mapped to the domain key SupervisorAgent uses.
_DEFERRAL_RE = re.compile(r"please ask the (\w+) agent", re.IGNORECASE)
_AGENT_NAME_TO_DOMAIN = {
    "underwriting": "underwriting",
    "claims": "claims",
    "analytics": "analytics",
}


def extract_deferral_target(answer: str) -> Optional[str]:
    """
    If `answer` is a "Please ask the X Agent" deferral, return the domain key the
    specialist is pointing to (e.g. "claims"), else None.

    A specialist's own SYSTEM_PROMPT recognizes when a question is out of its
    scope and names the right sibling — this just reads that back so the
    supervisor can transparently re-route instead of surfacing the deferral
    text as if it were the final answer.
    """
    match = _DEFERRAL_RE.search(answer)
    if not match:
        return None
    return _AGENT_NAME_TO_DOMAIN.get(match.group(1).lower())


def unwrap_raw_action_json(answer: str) -> str:
    """
    Some models occasionally emit the raw ReAct action JSON blob
    (`{"action": "Final Answer", "action_input": "..."}`) as the agent's final
    output instead of having it parsed down to just the action_input — a known
    brittleness of LangChain's regex-based structured-chat output parser that
    varies by model (observed with openai/gpt-oss-120b, not with the Llama model
    this app previously used). Detect and unwrap it so the leaked JSON scaffolding
    never reaches the user. Returns `answer` unchanged if it isn't this shape.
    """
    text = answer.strip()
    if not (text.startswith("{") and '"action"' in text and '"action_input"' in text):
        return answer
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return answer
    if isinstance(parsed, dict) and isinstance(parsed.get("action_input"), str):
        return parsed["action_input"]
    return answer


def validate_tabular_output(text: str) -> List[str]:
    """
    Check whether `text` meets the required output format rules.

    Returns a list of violation strings (empty list = valid):
      "no_markdown_table"   — no | col | row | found
      "no_comment_section"  — **Comment** section missing
    """
    violations: List[str] = []

    if not re.search(r"^\|.+\|", text, re.MULTILINE):
        violations.append("no_markdown_table")

    if not re.search(r"\*\*Comment", text):
        violations.append("no_comment_section")

    return violations


def enforce_tabular_format(answer: str, llm, skip: bool = False) -> str:
    """
    If `answer` is missing a markdown table, call the LLM directly to reformat it.

    Uses a focused single llm.invoke() call rather than re-running the full ReAct
    agent loop — faster, cheaper, and more reliably produces a table because the
    agent's tool-selection loop is bypassed entirely.

    Only triggers for the missing-table violation; a missing Comment section does
    not cause a retry.  Returns the original answer on any error.

    `skip=True` bypasses this entirely — for the greeting agent's conversational
    prose, which is correct as plain text and should never be coerced into a table.
    """
    if skip:
        return answer

    # Deferrals ("Please ask the Claims Agent") carry no data — reformatting
    # them into a table would just produce a nonsense one-cell table.
    if re.search(r"please ask the \w+ agent", answer, re.IGNORECASE):
        return answer

    violations = validate_tabular_output(answer)
    if "no_markdown_table" not in violations:
        return answer

    from langchain.schema import HumanMessage, SystemMessage

    try:
        response = llm.invoke(
            [
                SystemMessage(
                    content=(
                        "You are a formatting assistant for an insurance analytics chatbot.\n"
                        "Reformat the answer below as a proper markdown table.\n\n"
                        "Rules:\n"
                        "- Present ALL data using markdown table syntax: | Col | Col |\n"
                        "- Include a separator row: |---|---|\n"
                        "- Add a **Comment** section with 2-3 bullet insights after the table\n"
                        "- Do not omit any information from the original answer\n"
                        "- Never use prose or bullet lists for the data itself"
                    )
                ),
                HumanMessage(content=f"Reformat this as a markdown table:\n\n{answer}"),
            ]
        )
        return response.content.strip()
    except Exception:
        return answer
