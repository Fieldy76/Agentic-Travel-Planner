# Agentic Travel Workflow

A production-ready, framework-free Agentic Workflow for travel planning built with Python and the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/).

## 🚀 Features

### Core Capabilities
- **Framework-Free**: Built from scratch using standard Python libraries, demonstrating a deep understanding of agentic architectures.
- **MCP Integration**: Implements a custom, lightweight MCP Client/Server architecture for standardized tool communication.
- **Multi-LLM Support**: Seamlessly switch between OpenAI, Anthropic, and Google Gemini models.
- **Integrated Tools**:
    - ✈️ **Flight Search & Booking**: Find and book flights with ease.
        - Full airline names (e.g., "Delta Air Lines" instead of "DL")
        - Clickable booking links to airline websites
        - Localized pricing based on origin airport (USD, EUR, GBP, JPY)
        - Alternative flight suggestions when no results found
    - 🚗 **Car Rental**: Reserve vehicles for your trip.
    - ☀️ **Weather Forecast**: Automatically fetched with flight searches.
    - 💳 **Payments**: Secure payment processing simulation.
    - 📅 **Relative Date Handling**: Natural language date support ("tomorrow", "in 2 days", "next week").
- **Interactive CLI & Web UI**: Interact with the agent via a simple terminal interface or a modern, polished Web UI.
- **📜 Search History**: Full conversation history with localStorage persistence, delete individual conversations, and quick access to previous queries.

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

> [!TIP]
> If using VS Code, the included `.vscode/settings.json` will automatically hide `__pycache__` folders for a cleaner workspace.

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

    > [!IMPORTANT]
    > The application will automatically load these keys from the `.env` file. Ensure this file exists in the root directory before running the application.

## 🏃 Usage

### Web Interface (Recommended)
Start the Flask web server:
```bash
python web_server.py
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

### Web UI Features

The web interface includes:
- **💬 Chat Interface**: Modern, responsive chat UI with message history
- **🎨 Modern Premium Design**: 
  - Purple-blue gradient color scheme
  - Glassmorphism effects with backdrop blur
  - Smooth cubic-bezier animations
  - Glowing effects on interactive elements
  - Radial gradient background overlays
  - Enhanced depth with modern shadows
- **🔗 Clickable Links**: Flight booking links rendered as clickable elements
- **⏳ Thinking Indicator**: Animated "Thinking..." bubble shows agent activity
- **📜 Collapsible Search History Sidebar**: 
  - Starts collapsed for a cleaner initial view
  - Animated chevron icon rotates on toggle
  - View and restore full conversation history
  - Delete individual conversations with trash icon
  - Click any history item to restore that conversation
  - Smart timestamps (e.g., "5m ago", "2h ago", "3d ago")
  - Clear all history with confirmation
  - Persistent storage using localStorage (up to 50 conversations)
- **✈️ Flexible Flight Booking**:
  - Accept multiple selection formats (flight codes, numbers, or natural language)
  - Clear confirmation messages with booking reference and details
- **📊 Real-time Status**: Live updates as the agent processes tools

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
├── web_server.py           # Flask Web Server (Entry Point)
├── static/                 # Frontend Assets
│   ├── index.html
│   ├── css/
│   └── js/
├── travel_agent/
│   ├── main.py             # CLI Entry point
│   ├── config.py           # Configuration management
│   ├── agent/
│   │   ├── llm.py          # LLM Provider wrappers
│   │   ├── orchestrator.py # Core agent logic
│   │   ├── memory.py       # Conversation memory
│   │   └── cache.py        # Performance caching
│   ├── mcp/
│   │   ├── protocol.py     # MCP JSON-RPC definitions
│   │   └── mcp_server.py   # MCP Server implementation
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

- [Annotated Web Server](annotated/web_server.py)
- [Annotated Main Entry Point](annotated/travel_agent/main.py)
- [Annotated Agent Orchestrator](annotated/travel_agent/agent/orchestrator.py)
- [Annotated MCP Server](annotated/travel_agent/mcp/mcp_server.py)

## 📜 API Attribution

This application uses the following third-party APIs:

- **[Open-Meteo](https://open-meteo.com/)** - Weather forecast data (Licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/))
- **[Amadeus for Developers](https://developers.amadeus.com/)** - Flight search and booking data (Test environment)

For detailed license information and attribution requirements, please see [LICENSES.md](LICENSES.md).

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[MIT](LICENSE)
