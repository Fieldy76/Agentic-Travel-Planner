import os
import sys
import json
import logging
from flask import Flask, request, jsonify, Response, send_from_directory
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
load_dotenv()

from travel_agent.config import Config
from travel_agent.agent.llm import get_llm_provider
from travel_agent.mcp.mcp_server import MCPServer
from travel_agent.agent.orchestrator import AgentOrchestrator
from travel_agent.tools import (
    search_flights, 
    book_flight, 
    rent_car, 
    get_forecast, 
    process_payment,
    get_current_datetime
)

app = Flask(__name__, static_folder='static')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Agent Global Variable
agent = None


def initialize_agent():
    global agent
    
    # La validazione della configurazione dovrebbe ora superare il test se ANTHROPIC_API_KEY è presente.
    if not Config.validate(): 
        logger.error("Config validation failed.")
        return False
    
    # 1. SETUP: Inizializza i valori per il routing
    provider_name = os.getenv("LLM_PROVIDER", "ANTHROPIC").lower()
    api_key = None
    
    # Dizionario di tutti i provider disponibili in ordine di fallback
    # Puoi cambiare l'ordine a seconda delle tue preferenze
    provider_map = {
        "anthropic": Config.ANTHROPIC_API_KEY,
        "openai": Config.OPENAI_API_KEY,
        "google": Config.GOOGLE_API_KEY,
    }

    # 2. LOGICA DI ROUTING FLESSIBILE: Cerca la chiave del provider preferito
    
    # Tenta prima il provider specificato in LLM_PROVIDER
    if provider_name in provider_map and provider_map[provider_name]:
        api_key = provider_map[provider_name]
        
    # Se la chiave preferita manca, cerca un fallback valido
    if not api_key:
        logger.warning(
            f"La chiave API per il provider preferito ({provider_name.upper()}) è mancante o vuota. Ricerca di provider alternativi..."
        )
        
        # Iterazione su tutti i provider per il primo con una chiave valida
        for name, key in provider_map.items():
            if key:
                provider_name = name
                api_key = key
                logger.info(f"Trovata chiave valida per il provider di fallback: {provider_name.upper()}")
                break # Esci dal ciclo appena ne trovi uno

    # 3. INIZIALIZZAZIONE DELL'AGENTE (Solo se abbiamo una chiave valida)
    if not api_key:
        logger.error("Nessuna chiave LLM API valida trovata per inizializzare l'agente reale.")
        return False

    try:
        # Chiama il tuo router LLM con il provider e la chiave trovati
        llm = get_llm_provider(provider_name, api_key)
    except ImportError as e:
        logger.error(f"Errore nell'inizializzazione dell'LLM (SDK mancante?): {e}")
        return False

    # Il resto della tua logica di inizializzazione
    server = MCPServer()
    server.register_tool(search_flights)
    server.register_tool(book_flight)
    server.register_tool(rent_car)
    server.register_tool(get_forecast)
    server.register_tool(process_payment)
    server.register_tool(get_current_datetime)  # New tool for date/time awareness

    agent = AgentOrchestrator(llm, server)
    logger.info(f"Agente inizializzato con successo usando: {provider_name.upper()}")
    return True
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

@app.route('/api/chat', methods=['POST'])
def chat():
    if not agent:
        return jsonify({"error": "Agent not initialized"}), 500
    
    data = request.json
    user_input = data.get('message')
    
    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    def generate():
        for event in agent.run_generator(user_input):
            yield json.dumps(event) + "\n"

    return Response(generate(), mimetype='application/x-ndjson')

if __name__ == '__main__':
    if not initialize_agent():
        logger.warning("Agent initialization failed. Using Mock Agent for UI testing.")
        
        class MockAgent:
            def run_generator(self, user_input, request_id="mock"):
                yield {"type": "message", "content": f"I received your message: '{user_input}'. (Mock Agent)"}
                yield {"type": "tool_call", "name": "mock_tool", "arguments": {"query": "test"}}
                import time
                time.sleep(1)
                yield {"type": "tool_result", "name": "mock_tool", "content": "Mock result", "is_error": False}
                yield {"type": "message", "content": "This is a mock response because API keys are missing."}

        agent = MockAgent()

    app.run(debug=True, port=5000)
