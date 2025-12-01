import unittest
from unittest.mock import MagicMock
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from travel_agent.mcp.server import MCPServer
from travel_agent.agent.orchestrator import AgentOrchestrator
from travel_agent.tools import search_flights, book_flight, rent_car, get_forecast, process_payment

class TestTravelAgent(unittest.TestCase):
    def setUp(self):
        self.server = MCPServer()
        self.server.register_tool(search_flights)
        self.server.register_tool(book_flight)
        self.server.register_tool(rent_car)
        self.server.register_tool(get_forecast)
        self.server.register_tool(process_payment)
        
        self.mock_llm = MagicMock()
        self.agent = AgentOrchestrator(self.mock_llm, self.server)

    def test_tool_registration(self):
        tools = self.server.list_tools()
        tool_names = [t["name"] for t in tools]
        self.assertIn("search_flights", tool_names)
        self.assertIn("book_flight", tool_names)
        self.assertIn("rent_car", tool_names)
        self.assertIn("get_forecast", tool_names)
        self.assertIn("process_payment", tool_names)

    def test_flight_search_tool(self):
        result = self.server.call_tool("search_flights", {
            "origin": "JFK",
            "destination": "LHR",
            "date": "2023-12-25"
        })
        self.assertFalse(result.isError)
        self.assertIn("JFK", result.content[0]["text"])

    def test_agent_flow(self):
        # Simulate a simple flow: User asks -> LLM calls tool -> Tool returns -> LLM answers
        
        # 1. User Input
        user_input = "Find flights from NYC to London on 2023-12-25"
        
        # 2. Mock LLM response to call tool
        self.mock_llm.call_tool.side_effect = [
            {
                "content": "Searching for flights...",
                "tool_calls": [{
                    "id": "call_1",
                    "name": "search_flights",
                    "arguments": {"origin": "NYC", "destination": "LON", "date": "2023-12-25"}
                }]
            },
            {
                "content": "I found several flights.",
                "tool_calls": None
            }
        ]
        
        # Run agent
        self.agent.run(user_input)
        
        # Verify LLM was called twice
        self.assertEqual(self.mock_llm.call_tool.call_count, 2)
        
        # Verify message history contains tool result in correct format
        # Expected history: [User, Assistant(ToolCall), ToolResult, Assistant(Final)]
        self.assertEqual(len(self.agent.messages), 4)
        self.assertEqual(self.agent.messages[2]["role"], "tool")
        self.assertEqual(self.agent.messages[2]["tool_call_id"], "call_1")
        self.assertIn("NYC", self.agent.messages[2]["content"])
        
if __name__ == "__main__":
    unittest.main()
