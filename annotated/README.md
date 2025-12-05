# Annotated Codebase

This directory contains key files from the **Agentic Travel Workflow** that have been annotated with detailed comments for educational purposes. 

These files explain the "why" and "how" behind the implementation choices, making it easier to understand:

- **Asynchronous Agent Architecture**: How we handle non-blocking LLM calls and tool execution.
- **Model Context Protocol (MCP)**: How we structure communication between the agent and its tools.
- **Pydantic Validation**: How we enforce strict types for arguments.
- **FastAPI Integration**: How we serve the agent over a modern web framework.

## Available Annotated Files

### 1. [web_server.py](web_server.py)
The entry point for the Web Interface. Learn how we:
- Initialize the `FastAPI` app.
- Set up the SSE (Server-Sent Events) stream for real-time chat.
- Handle CORS and static files.

### 2. [travel_agent/cli.py](travel_agent/cli.py)
The CLI entry point. Learn how we:
- Load configuration and API keys.
- Initialize the Async Event Loop.
- Run the agent in a terminal session.

### 3. [travel_agent/agent/orchestrator.py](travel_agent/agent/orchestrator.py)
The brain of the operation. Learn how we:
- Managing the Agent Loop (Thought -> Plan -> Action).
- Handle LLM API calls with retries.
- Execute tools and feed results back to context.

### 4. [travel_agent/mcp/mcp_server.py](travel_agent/mcp/mcp_server.py)
The Tool Manager. Learn how we:
- Register Python functions as tools.
- Inspect function signatures to generate JSON schemas automatically.
- Route tool calls to their implementations.

---

> **Note**: These files are copies of the actual source code, but with extensive comments added. For the executable code used in production, please refer to the root directories.
