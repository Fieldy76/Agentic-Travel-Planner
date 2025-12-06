# Annotated Codebase

This directory contains the **complete** annotated version of the **Agentic Travel Workflow** codebase for educational purposes.

Every file includes detailed comments explaining:

- **Asynchronous Agent Architecture**: Non-blocking LLM calls and tool execution
- **Model Context Protocol (MCP)**: Communication structure between agent and tools
- **Pydantic Validation**: Strict type enforcement for arguments
- **FastAPI Integration**: Modern web framework with streaming responses
- **Multi-Provider LLM Support**: OpenAI, Anthropic, and Google Gemini
- **Frontend Architecture**: Chat UI, history management, and styled modals

## Available Annotated Files

### Core Application

| File | Description |
|------|-------------|
| [web_server.py](web_server.py) | FastAPI app, SSE streaming, file uploads, CORS configuration |

### Agent Module (`travel_agent/agent/`)

| File | Description |
|------|-------------|
| [orchestrator.py](travel_agent/agent/orchestrator.py) | Core agent loop, LLM reasoning, tool execution, retry logic |
| [llm.py](travel_agent/agent/llm.py) | Multi-provider LLM abstraction (OpenAI, Anthropic, Google) |
| [memory.py](travel_agent/agent/memory.py) | Conversation history management with abstract interface |
| [cache.py](travel_agent/agent/cache.py) | Performance caching for tool results |

### MCP Module (`travel_agent/mcp/`)

| File | Description |
|------|-------------|
| [mcp_server.py](travel_agent/mcp/mcp_server.py) | Tool registration, JSON schema generation, execution |
| [protocol.py](travel_agent/mcp/protocol.py) | MCP data types, JSON-RPC definitions, Pydantic models |

### Tools Module (`travel_agent/tools/`)

| File | Description |
|------|-------------|
| [flights.py](travel_agent/tools/flights.py) | Flight search (Amadeus API) and booking with mock fallback |
| [payment.py](travel_agent/tools/payment.py) | Stripe Payment Intents integration with error handling |
| [weather.py](travel_agent/tools/weather.py) | Weather forecast (Open-Meteo API) with caching |
| [cars.py](travel_agent/tools/cars.py) | Car rental reservations (mock implementation) |
| [datetime_tool.py](travel_agent/tools/datetime_tool.py) | Current date/time utility for the agent |

### Configuration

| File | Description |
|------|-------------|
| [travel_agent/cli.py](travel_agent/cli.py) | CLI entry point, async event loop, REPL interface |
| [travel_agent/config.py](travel_agent/config.py) | Environment variables, API key management, JSON logging |

### Frontend (`static/`)

| File | Description |
|------|-------------|
| [index.html](static/index.html) | Main SPA structure, modals, toast notifications |
| [css/style.css](static/css/style.css) | Gemini-inspired UI, Material Design 3, animations |
| [js/app.js](static/js/app.js) | Chat logic, NDJSON streaming, history management |

## Comment Style

Each file includes:

1. **Module Header** - Comprehensive docstring with architecture diagrams
2. **Section Dividers** - Clear separation of logical code blocks
3. **Inline Comments** - Line-by-line explanations of complex logic
4. **Docstrings** - Full parameter and return value documentation
5. **Examples** - Usage examples in function documentation

## Example Annotation

```python
# =============================================================================
# AGENT ORCHESTRATOR CLASS
# =============================================================================

class AgentOrchestrator:
    """
    The central orchestrator that coordinates LLM reasoning with tool execution.
    
    This class implements the agentic loop pattern where the LLM can:
    1. Reason about the user's request
    2. Decide which tools to call (if any)
    3. Execute tools and observe results
    4. Continue reasoning based on tool outputs
    5. Provide a final response
    """
```

---

> **Note**: These files mirror production code with added comments. Refer to root directories for executable versions without annotations.
