"""Expression guidance stays data-driven and does not require literal replay."""
import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_central_server"))
from restricted_rag import NEXI_MEMORY_INSTRUCTION, build_grounded_prompt


@pytest.mark.parametrize("records", [
    [{"type": "fact", "data": {"subject": "My favorite color", "predicate": "is", "object": "blue"}}],
    [{"type": "object", "data": {"name": "My travel mug"}}],
    [{"type": "fact", "data": {"subject": "My favorite color", "predicate": "is", "object": "blue"}},
     {"type": "object", "data": {"name": "My travel mug"}}],
])
def test_central_policy_allows_natural_expression_without_new_claims(records):
    prompt, texts = build_grounded_prompt("My favorite color and my travel mug", records)
    assert prompt.startswith(NEXI_MEMORY_INSTRUCTION)
    assert prompt.count(NEXI_MEMORY_INSTRUCTION) == 1
    assert "preserving factual meaning exactly" in prompt
    assert "not their exact wording" in prompt
    assert "retaining their wording" not in prompt
    assert "using the stored wording" not in prompt
    assert all(text in prompt for text in texts)


def test_expression_instructions_contain_no_domain_specific_response_templates():
    source = inspect.getsource(build_grounded_prompt) + NEXI_MEMORY_INSTRUCTION
    assert not any(word in source.casefold() for word in ("hometown", "water bottle", "phone", "university"))
