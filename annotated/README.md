# Annotated Codebase

This directory contains key files from the **Agentic Travel Workflow** annotated for educational purposes.

These files explain the "why" and "how" behind implementation choices:

- **Asynchronous Agent Architecture**: Non-blocking LLM calls and tool execution.
- **Model Context Protocol (MCP)**: Communication structure between agent and tools.
- **Pydantic Validation**: Strict type enforcement for arguments.
- **FastAPI Integration**: Modern web framework serving.
- **Frontend Architecture**: Chat UI, history management, and styled modals.

## Available Annotated Files

### Backend

| File | Description |
|------|-------------|
| [web_server.py](web_server.py) | FastAPI app, SSE streaming, file uploads |
| [travel_agent/cli.py](travel_agent/cli.py) | CLI entry point, async event loop |
| [travel_agent/agent/orchestrator.py](travel_agent/agent/orchestrator.py) | Agent loop, LLM calls, tool execution |
| [travel_agent/agent/llm.py](travel_agent/agent/llm.py) | Multi-provider LLM support (OpenAI, Anthropic, Google) |
| [travel_agent/mcp/mcp_server.py](travel_agent/mcp/mcp_server.py) | Tool registration, JSON schema generation |
| [travel_agent/tools/flights.py](travel_agent/tools/flights.py) | Flight search and booking |

### Frontend

| File | Description |
|------|-------------|
| [static/index.html](static/index.html) | Main SPA structure, modals, toast notifications |
| [static/css/style.css](static/css/style.css) | Modern UI styling, animations, responsive design |
| [static/js/app.js](static/js/app.js) | Chat logic, history management, context menus |

---

> **Note**: These files mirror production code. Refer to root directories for executable versions.
