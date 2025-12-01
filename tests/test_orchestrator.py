import unittest
from unittest.mock import MagicMock
from travel_agent.agent.orchestrator import AgentOrchestrator
from travel_agent.mcp.server import MCPServer
from travel_agent.agent.memory import InMemoryMemory

class TestOrchestrator(unittest.TestCase):
    def setUp(self):
        self.mock_llm = MagicMock()
        self.mock_server = MagicMock()
        self.memory = InMemoryMemory()
        self.agent = AgentOrchestrator(self.mock_llm, self.mock_server, self.memory)

    def test_initialization(self):
        self.assertIsInstance(self.agent.memory, InMemoryMemory)

    def test_run_basic_flow(self):
        # Setup mocks
        self.mock_server.list_tools.return_value = []
        self.mock_llm.call_tool.return_value = {
            "content": "Hello",
            "tool_calls": None
        }
        
        self.agent.run("Hi")
        
        # Verify memory
        messages = self.memory.get_messages()
        self.assertEqual(len(messages), 2) # User + Assistant
        self.assertEqual(messages[0]["content"], "Hi")
        self.assertEqual(messages[1]["content"], "Hello")

    def test_tool_execution_retry(self):
        # Setup mocks for tool call
        self.mock_server.list_tools.return_value = []
        
        # First LLM call returns a tool call
        # Second LLM call returns final answer
        self.mock_llm.call_tool.side_effect = [
            {
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "name": "test_tool",
                    "arguments": {}
                }]
            },
            {
                "content": "Done",
                "tool_calls": None
            }
        ]
        
        # Mock server tool call to fail once then succeed
        mock_result = MagicMock()
        mock_result.content = [{"text": "Success"}]
        mock_result.isError = False
        
        self.mock_server.call_tool.side_effect = [
            Exception("Temporary failure"),
            mock_result
        ]
        
        self.agent.run("Do something")
        
        # Verify call_tool was called twice (retry)
        self.assertEqual(self.mock_server.call_tool.call_count, 2)
        
        
        # Verify memory contains tool result
        # Expected: [user, tool, assistant(final)] - no assistant message when content is None
        messages = self.memory.get_messages()
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[1]["role"], "tool")
        self.assertEqual(messages[1]["content"], "Success")
        self.assertEqual(messages[2]["role"], "assistant")
        self.assertEqual(messages[2]["content"], "Done")

if __name__ == "__main__":
    unittest.main()
