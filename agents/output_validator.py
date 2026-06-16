"""
Output format validation and enforcement for specialist agent responses.

All specialist system prompts require:
  1. A markdown table for any structured data
  2. A **Comment** section with bullet insights

validate_tabular_output()  — pure string check, no LLM needed (fast, testable)
enforce_tabular_format()   — calls llm.invoke() to reformat if a table is missing
"""

import re
from typing import List


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


def enforce_tabular_format(answer: str, llm) -> str:
    """
    If `answer` is missing a markdown table, call the LLM directly to reformat it.

    Uses a focused single llm.invoke() call rather than re-running the full ReAct
    agent loop — faster, cheaper, and more reliably produces a table because the
    agent's tool-selection loop is bypassed entirely.

    Only triggers for the missing-table violation; a missing Comment section does
    not cause a retry.  Returns the original answer on any error.
    """
    violations = validate_tabular_output(answer)
    if "no_markdown_table" not in violations:
        return answer

    from langchain.schema import HumanMessage, SystemMessage
    try:
        response = llm.invoke([
            SystemMessage(content=(
                "You are a formatting assistant for an insurance analytics chatbot.\n"
                "Reformat the answer below as a proper markdown table.\n\n"
                "Rules:\n"
                "- Present ALL data using markdown table syntax: | Col | Col |\n"
                "- Include a separator row: |---|---|\n"
                "- Add a **Comment** section with 2-3 bullet insights after the table\n"
                "- Do not omit any information from the original answer\n"
                "- Never use prose or bullet lists for the data itself"
            )),
            HumanMessage(content=f"Reformat this as a markdown table:\n\n{answer}"),
        ])
        return response.content.strip()
    except Exception:
        return answer
