# Agentic Travel Workflow

A production-ready, framework-free Agentic Workflow for travel planning built with Python and the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/).

## 🚀 Features

### Core Capabilities
- **Framework-Free**: Built from scratch using standard Python libraries, demonstrating a deep understanding of agentic architectures.
- **MCP Integration**: Implements a custom, lightweight MCP Client/Server architecture for standardized tool communication.
- **Multi-LLM Support**: Seamlessly switch between OpenAI, Anthropic, and Google Gemini models.
- **Integrated Tools**:
    - ✈️ **Flight Search & Booking**: Find and book flights with ease.
    - 🚗 **Car Rental**: Reserve vehicles for your trip.
    - ☀️ **Weather Forecast**: Check conditions before you travel.
    - 💳 **Payments**: Secure payment processing simulation.
- **Interactive CLI & Web UI**: Interact with the agent via a simple terminal interface or a modern, polished Web UI.

### Production-Ready Features
- **📊 Structured Logging**: JSON-formatted logs with `request_id`, `timestamp`, and contextual metadata for observability.
- **✅ Pydantic Validation**: Strict type validation for all MCP protocol messages and tool inputs/outputs.
- **🔄 Error Handling & Retries**: Exponential backoff retry logic for resilient tool execution.
- **💾 State Management**: Abstract memory interface with in-memory implementation for conversation persistence.
- **⚡ Performance Caching**: TTL-based caching for expensive API calls (flights, weather).
- **🧪 Comprehensive Testing**: 9 unit and integration tests covering protocol validation, orchestrator logic, and full workflows.
- **🐳 Docker Support**: Multi-stage Dockerfile with security best practices (non-root user).

## 🛠️ Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/yourusername/agentic-travel-workflow.git
    cd agentic-travel-workflow
    ```

2.  **Create and activate a virtual environment**:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## ⚙️ Configuration

1.  Copy the example environment file:
    ```bash
    cp .env.example .env
    ```

2.  Open `.env` and add your API keys:
    ```ini
    # LLM API Keys (At least one is required)
    OPENAI_API_KEY=sk-...
    ANTHROPIC_API_KEY=sk-ant-...
    GOOGLE_API_KEY=AIza...

    # Optional Service Keys (Mocks used if missing)
    FLIGHT_API_KEY=...
    ```

## 🏃 Usage

### Web Interface (Recommended)
Start the Flask web server:
```bash
python server.py
```
Open your browser and navigate to `http://localhost:5000`.

### Command Line Interface
Start the CLI agent:
```bash
python travel_agent/main.py
```

**Example Interaction:**
```
You: I want to plan a trip to Tokyo next month.
Agent: I'd love to help you plan your trip to Tokyo! When exactly are you thinking of going?
You: From December 10th to December 20th.
Agent: Great! Let me check flights and weather for you...
```

## 🧪 Testing

Run the comprehensive test suite:
```bash
# Activate virtual environment first
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Run all tests
python -m unittest discover tests -v
```

**Test Coverage**:
- Protocol validation (Pydantic models)
- Orchestrator logic (error handling, retries, memory)
- Full integration workflows

## 📂 Project Structure

```
├── server.py               # Flask Web Server
├── static/                 # Frontend Assets
│   ├── index.html
│   ├── css/
│   └── js/
├── travel_agent/
│   ├── main.py             # CLI Entry point
│   ├── config.py           # Configuration management
│   ├── agent/
│   │   ├── llm.py          # LLM Provider wrappers
│   │   └── orchestrator.py # Core agent logic (The "Brain")
│   ├── mcp/
│   │   ├── protocol.py     # MCP JSON-RPC definitions
│   │   └── server.py       # Custom MCP Server implementation
│   └── tools/              # Tool implementations
│       ├── flights.py
│       ├── cars.py
│       ├── weather.py
│       └── payment.py
```

## 🐳 Deployment

Build and run with Docker:
```bash
# Build the image
docker build -t travel-agent .

# Run the container
docker run -p 5000:5000 --env-file .env travel-agent
```

The Docker image uses a multi-stage build and runs as a non-root user for security.

## 📚 Educational Resources

For those learning about agentic workflows, I have included a fully **annotated version of the codebase** in the `annotated/` directory. Every line of code in this directory is commented to explain its purpose and functionality.

- [Annotated Web Server](annotated/server.py)
- [Annotated Main Entry Point](annotated/travel_agent/main.py)
- [Annotated Agent Orchestrator](annotated/travel_agent/agent/orchestrator.py)
- [Annotated MCP Server](annotated/travel_agent/mcp/server.py)

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[MIT](LICENSE)
