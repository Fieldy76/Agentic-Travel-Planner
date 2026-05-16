"""End-to-end orchestrator tests with a stubbed LLM and a real MCPServer."""

import pytest

from travel_agent.agent.memory import InMemoryMemory
from travel_agent.agent.orchestrator import AgentOrchestrator, _redact_pii
from travel_agent.mcp.mcp_server import MCPServer


def _server_with(tool):
    s = MCPServer()
    s.register_tool(tool)
    return s


class ScriptedLLM:
    model = "scripted"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    async def call_tool(self, messages, tools):
        self.calls += 1
        if self.responses:
            return self.responses.pop(0)
        return {"content": "fallback", "tool_calls": None}


# Helpers
async def _drain(agent, prompt="hi"):
    events = []
    async for e in agent.run_generator(prompt):
        events.append(e)
    return events


def fake_tool(x: int) -> dict:
    return {"got": x}


def fake_tool_fails(x: int):
    raise RuntimeError("boom")


async def test_no_tool_call_returns_message_and_stores():
    llm = ScriptedLLM({"content": "hello", "tool_calls": None})
    agent = AgentOrchestrator(llm, MCPServer(), InMemoryMemory())
    events = await _drain(agent)
    types = [e["type"] for e in events]
    assert types == ["message"]
    assert events[0]["content"] == "hello"
    assert len(agent.memory.get_messages()) == 2  # user + assistant


async def test_single_tool_call_then_message():
    llm = ScriptedLLM(
        {"content": None, "tool_calls": [{"id": "t1", "name": "fake_tool", "arguments": {"x": 7}}]},
        {"content": "done", "tool_calls": None},
    )
    agent = AgentOrchestrator(llm, _server_with(fake_tool), InMemoryMemory())
    events = await _drain(agent)
    assert [e["type"] for e in events] == ["tool_call", "tool_result", "message"]
    assert events[1]["is_error"] is False


async def test_max_turns_caps_loop(monkeypatch):
    # Force a tight cap and make LLM always ask for the tool.
    from travel_agent.config import Config
    monkeypatch.setattr(Config, "MAX_TURNS", 2)
    llm = ScriptedLLM(
        {"content": None, "tool_calls": [{"id": "t", "name": "fake_tool", "arguments": {"x": 1}}]},
        {"content": None, "tool_calls": [{"id": "t", "name": "fake_tool", "arguments": {"x": 1}}]},
        {"content": "must not reach", "tool_calls": None},
    )
    agent = AgentOrchestrator(llm, _server_with(fake_tool), InMemoryMemory())
    events = await _drain(agent)
    # Should stop after MAX_TURNS turns, never emitting the third response's message.
    assert all(e.get("content") != "must not reach" for e in events)
    assert llm.calls == 2


async def test_failing_tool_yields_error_then_continues(monkeypatch):
    from travel_agent.config import Config
    monkeypatch.setattr(Config, "MAX_TOOL_RETRIES", 1)
    llm = ScriptedLLM(
        {"content": None, "tool_calls": [{"id": "t", "name": "fake_tool_fails", "arguments": {"x": 1}}]},
        {"content": "I'll try something else", "tool_calls": None},
    )
    agent = AgentOrchestrator(llm, _server_with(fake_tool_fails), InMemoryMemory())
    events = await _drain(agent)
    # The MCPServer catches the RuntimeError and returns isError=True.
    assert any(e["type"] == "tool_result" and e["is_error"] for e in events)


async def test_llm_failure_yields_error_event(monkeypatch):
    from travel_agent.config import Config
    monkeypatch.setattr(Config, "MAX_LLM_RETRIES", 1)

    class FailingLLM:
        model = "fail"
        async def call_tool(self, messages, tools):
            raise RuntimeError("network")

    agent = AgentOrchestrator(FailingLLM(), MCPServer(), InMemoryMemory())
    events = await _drain(agent)
    assert events == [{"type": "error", "content": "I'm having trouble reaching the language model. Please try again in a moment."}]


def test_redact_pii():
    s = "email me at alice@example.com or call 12345678901"
    assert _redact_pii(s) == "email me at [email] or call [digits]"


async def test_document_attachment_extracts_text(tmp_path):
    """When a TXT upload is supplied, its content lands in the user message."""
    llm = ScriptedLLM({"content": "got it", "tool_calls": None})
    agent = AgentOrchestrator(llm, MCPServer(), InMemoryMemory())
    file_bytes = b"itinerary text"
    events = []
    async for e in agent.run_generator("summarize my trip", file_data=file_bytes, mime_type="text/plain"):
        events.append(e)
    user_msg = agent.memory.get_messages()[0]
    assert "itinerary text" in user_msg["content"]
    assert "ATTACHED DOCUMENT" in user_msg["content"]
