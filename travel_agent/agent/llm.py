import os
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import json

# Import SDKs
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

try:
    import google.generativeai as genai
    from google.protobuf import struct_pb2
except ImportError:
    genai = None

class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text from the LLM."""
        pass

    @abstractmethod
    def call_tool(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate a response that might include a tool call."""
        pass

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        if not OpenAI:
            raise ImportError("OpenAI SDK not installed.")
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )
        return response.choices[0].message.content

    def call_tool(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        # OpenAI expects strict role structure: system -> [user, assistant, tool]*
        # Our generic 'tool' role maps directly to OpenAI's 'tool' role
        
        openai_tools = []
        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {})
                }
            })

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=openai_tools if openai_tools else None,
            tool_choice="auto" if openai_tools else None
        )
        
        message = response.choices[0].message
        
        if message.tool_calls:
            tool_calls = []
            for tc in message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments)
                })
            return {"content": message.content, "tool_calls": tool_calls}
        
        return {"content": message.content, "tool_calls": None}

class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        if not Anthropic:
            raise ImportError("Anthropic SDK not installed.")
        self.client = Anthropic(api_key=api_key)
        self.model = model

    def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        kwargs = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}]
        }
        if system_prompt:
            kwargs["system"] = system_prompt
            
        response = self.client.messages.create(**kwargs)
        return response.content[0].text

    def call_tool(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Anthropic Tool Use Format:
        # User: ...
        # Assistant: <tool_use>...</tool_use>
        # User: <tool_result>...</tool_result>
        
        anthropic_tools = []
        for tool in tools:
            anthropic_tools.append({
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get("inputSchema", {})
            })

        system_prompt = None
        converted_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            elif msg["role"] == "tool":
                # Convert generic 'tool' role to Anthropic 'user' role with tool_result content
                converted_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg["tool_call_id"],
                        "content": msg["content"]
                    }]
                })
            elif msg["role"] == "assistant" and "tool_calls" in msg:
                # Need to reconstruct the assistant message with tool_use blocks
                content_blocks = []
                if msg.get("content"):
                    content_blocks.append({"type": "text", "text": msg["content"]})
                
                # We need to find the tool calls associated with this message
                # In our generic format, they are stored in the message itself?
                # Wait, Orchestrator stores 'tool_calls' in the assistant message.
                # But Orchestrator logic: self.messages.append({"role": "assistant", "content": content})
                # It DOES NOT store tool_calls in the message history explicitly in the previous version!
                # I need to fix Orchestrator to store tool_calls in the assistant message too!
                
                # Let's assume Orchestrator IS fixed to store tool_calls (I will verify/fix this next)
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc["arguments"]
                        })
                
                converted_messages.append({
                    "role": "assistant",
                    "content": content_blocks
                })
            else:
                converted_messages.append(msg)

        kwargs = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": converted_messages,
            "tools": anthropic_tools
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = self.client.messages.create(**kwargs)
        
        tool_calls = []
        content_text = ""
        
        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input
                })
                
        return {"content": content_text, "tool_calls": tool_calls if tool_calls else None}

class GoogleProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-1.5-pro"):
        if not genai:
            raise ImportError("Google Generative AI SDK not installed.")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)

    def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"System: {system_prompt}\nUser: {prompt}"
        response = self.model.generate_content(full_prompt)
        return response.text

    def call_tool(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Basic Google Tool Support
        # Note: This is a best-effort implementation. 
        # Google's SDK manages history via ChatSession usually, but here we have stateless messages.
        
        google_tools = []
        for tool in tools:
            # Convert JSON Schema to Google FunctionDeclaration
            # This is complex to map perfectly, doing a simplified mapping
            google_tools.append({
                "function_declarations": [{
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {})
                }]
            })
            
        # Convert messages to Google Content format
        history = []
        for msg in messages:
            role = "user" if msg["role"] in ["user", "tool"] else "model"
            parts = []
            
            if msg["role"] == "tool":
                # Google expects FunctionResponse
                parts.append(genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=msg["name"],
                        response={"result": msg["content"]}
                    )
                ))
            elif msg["role"] == "assistant" and msg.get("tool_calls"):
                 # Google expects FunctionCall
                 for tc in msg["tool_calls"]:
                     parts.append(genai.protos.Part(
                         function_call=genai.protos.FunctionCall(
                             name=tc["name"],
                             args=tc["arguments"]
                         )
                     ))
            else:
                parts.append(genai.protos.Part(text=msg.get("content", "")))
                
            history.append(genai.protos.Content(role=role, parts=parts))

        # Generate
        # We need to use the chat interface to maintain history correctly with tools
        chat = self.model.start_chat(history=history[:-1] if history else [])
        last_msg = history[-1] if history else None
        
        # This is tricky because start_chat expects history, and we send the last message
        # But if the last message was a tool response, we need to send it carefully
        
        # Fallback: Just warn user
        return {"content": "Google Tool Calling requires complex protobuf mapping. Please use OpenAI or Anthropic for full tool support.", "tool_calls": None}

def get_llm_provider(provider_name: str, api_key: str) -> LLMProvider:
    if provider_name.lower() == "openai":
        return OpenAIProvider(api_key)
    elif provider_name.lower() == "anthropic":
        return AnthropicProvider(api_key)
    elif provider_name.lower() == "google":
        return GoogleProvider(api_key)
    else:
        raise ValueError(f"Unknown provider: {provider_name}")
