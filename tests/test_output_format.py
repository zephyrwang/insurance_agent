"""
Tests for output format validation (agents/output_validator.py).

These are pure-string tests — no LLM, no DB, no Streamlit context required.
They verify that validate_tabular_output() correctly catches non-table responses
so the enforcement layer has a reliable signal to trigger a re-prompt.
"""

import pytest
from agents.output_validator import validate_tabular_output

# ── Sample outputs ───────────────────────────────────────────────────────────

VALID_TABLE_WITH_COMMENT = """\
**Claims History — P-HIGH**

| Claim ID | Date       | Type      | Amount   | Status      |
|----------|------------|-----------|----------|-------------|
| TC-001   | 2024-01-01 | Collision | $12,000  | 🔴 Open     |
| TC-002   | 2024-06-01 | Theft     | $10,000  | 🔴 Open     |
| TC-003   | 2025-01-01 | Liability | $8,000   | ✅ Closed   |

**Comment**
- Two open collision/theft claims totaling $22,000 are a significant exposure.
- Total claim volume ($35,000 over 4 claims) exceeds the high-risk threshold.
- Recommend SIU referral given the fraud score of 7.
"""

PROSE_OUTPUT = """\
Person P-HIGH has filed 4 claims in the past 3 years totaling $35,000.
Two claims (TC-001 and TC-002) are currently open. The fraud risk is High
and an SIU referral is recommended.
"""

NUMBERED_LIST_OUTPUT = """\
P-HIGH's claims:
1. TC-001 - 2024-01-01 - Collision - $12,000 - Open
2. TC-002 - 2024-06-01 - Theft - $10,000 - Open
3. TC-003 - 2025-01-01 - Liability - $8,000 - Closed
"""

TABLE_WITHOUT_COMMENT = """\
| Claim ID | Date       | Amount  | Status  |
|----------|------------|---------|---------|
| TC-001   | 2024-01-01 | $12,000 | Open    |
"""

EMPTY_OUTPUT = ""

# ── validate_tabular_output tests ────────────────────────────────────────────

class TestValidateTabularOutput:
    def test_valid_output_returns_no_violations(self):
        assert validate_tabular_output(VALID_TABLE_WITH_COMMENT) == []

    def test_prose_output_flagged_as_no_table(self):
        violations = validate_tabular_output(PROSE_OUTPUT)
        assert "no_markdown_table" in violations

    def test_prose_output_flagged_as_no_comment(self):
        violations = validate_tabular_output(PROSE_OUTPUT)
        assert "no_comment_section" in violations

    def test_numbered_list_flagged_as_no_table(self):
        violations = validate_tabular_output(NUMBERED_LIST_OUTPUT)
        assert "no_markdown_table" in violations

    def test_table_without_comment_flagged(self):
        violations = validate_tabular_output(TABLE_WITHOUT_COMMENT)
        assert "no_comment_section" in violations
        assert "no_markdown_table" not in violations

    def test_empty_output_has_both_violations(self):
        violations = validate_tabular_output(EMPTY_OUTPUT)
        assert "no_markdown_table" in violations
        assert "no_comment_section" in violations

    def test_inline_pipe_not_counted_as_table(self):
        # A sentence with pipes (e.g. in prose) should not be mistaken for a table
        prose_with_pipe = "The answer is: High | Medium | Low risk categories exist."
        violations = validate_tabular_output(prose_with_pipe)
        # The regex requires the pipe to be at the START of a line (re.MULTILINE)
        assert "no_markdown_table" in violations

    def test_comment_case_variants(self):
        # Both **Comment** and **Comment:** should pass
        output_colon = VALID_TABLE_WITH_COMMENT.replace("**Comment**", "**Comment:**")
        assert "no_comment_section" not in validate_tabular_output(output_colon)


# ── enforce_tabular_format tests ─────────────────────────────────────────────

class TestEnforceTabularFormat:
    def _fake_llm(self, return_value=VALID_TABLE_WITH_COMMENT):
        """LLM stub whose .invoke() returns a fake AIMessage."""
        from unittest.mock import MagicMock
        llm = MagicMock()
        msg = MagicMock()
        msg.content = return_value
        llm.invoke.return_value = msg
        return llm

    def test_valid_answer_returned_unchanged(self):
        from agents.output_validator import enforce_tabular_format
        llm = self._fake_llm()
        result = enforce_tabular_format(VALID_TABLE_WITH_COMMENT, llm)
        assert result == VALID_TABLE_WITH_COMMENT
        llm.invoke.assert_not_called()

    def test_prose_answer_triggers_llm_reformat(self):
        from agents.output_validator import enforce_tabular_format
        llm = self._fake_llm(VALID_TABLE_WITH_COMMENT)
        result = enforce_tabular_format(PROSE_OUTPUT, llm)
        assert result == VALID_TABLE_WITH_COMMENT.strip()
        llm.invoke.assert_called_once()
        # Verify the reformat prompt contains the original prose
        call_args = llm.invoke.call_args[0][0]
        human_msg = call_args[-1]
        assert "PROSE_OUTPUT" not in human_msg.content  # sanity
        assert "Reformat" in human_msg.content

    def test_llm_exception_returns_original(self):
        from agents.output_validator import enforce_tabular_format
        from unittest.mock import MagicMock
        llm = MagicMock()
        llm.invoke.side_effect = RuntimeError("LLM unavailable")
        result = enforce_tabular_format(PROSE_OUTPUT, llm)
        assert result == PROSE_OUTPUT, "should fall back to original on LLM failure"
