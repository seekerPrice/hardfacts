"""uv run --with "mcp>=2.2" --with anyio --with pytest pytest -q integrations/mcp"""

import sys
from pathlib import Path

import pytest
from mcp import Client

sys.path.insert(0, str(Path(__file__).parent))
from server import server  # noqa: E402

ORDER = {"tracking": "EN123456789MY", "eta": "2026-10-03"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_the_tool_reports_an_invented_tracking_number():
    async with Client(server, raise_exceptions=True) as client:
        result = await client.call_tool("check_hard_facts", {"draft": "Tracking EN123456780MY, due 3 October.", "sources": [ORDER]})

    data = result.structured_content
    assert data["ok"] is False
    assert [u["text"] for u in data["unsupported"]] == ["EN123456780MY"]
    assert "EN123456780MY" in data["feedback"]


@pytest.mark.anyio
async def test_a_supported_draft_is_ok():
    async with Client(server, raise_exceptions=True) as client:
        result = await client.call_tool("check_hard_facts", {"draft": "Tracking EN123456789MY.", "sources": [ORDER], "kinds": ["identifier"]})

    assert result.structured_content["ok"] is True


@pytest.mark.anyio
async def test_a_calculation_shows_its_working_and_does_not_block_the_answer():
    kettle = {"current": {"price": 94.8}, "new": {"price": 101.12}}
    async with Client(server, raise_exceptions=True) as client:
        result = await client.call_tool("check_hard_facts", {
            "draft": "It's $101.12 and yours was $94.80, so you pay $6.32 more.", "sources": [kettle]})

    data = result.structured_content
    assert data["ok"] is False and data["ok_except_calculations"] is True
    assert [(u["text"], u["computed_as"]) for u in data["unsupported"]] == [("$6.32", "$101.12 − $94.80")]
