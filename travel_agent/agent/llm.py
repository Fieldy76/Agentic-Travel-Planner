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
                
                # CRITICAL FIX: Anthropic does not allow empty content blocks
                if not content_blocks:
                    # If we somehow have an empty assistant message, skip it or add placeholder
                    # This shouldn't happen with correct orchestrator logic, but safety first
                    continue 

                converted_messages.append({
                    "role": "assistant",
                    "content": content_blocks
                })
            else:
                # Regular user/system messages
                if not msg.get("content"):
                    continue # Skip empty messages
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
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        if not genai:
            raise ImportError("Google Generative AI SDK not installed.")
        genai.configure(api_key=api_key)
        
        # Configure safety settings to avoid blocking legitimate tool outputs
        self.safety_settings = {
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
        }
        
        self.model = genai.GenerativeModel(model)

    def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"System: {system_prompt}\nUser: {prompt}"
        response = self.model.generate_content(full_prompt)
        return response.text

    def call_tool(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Questa implementazione gestisce la conversione di messaggi e strumenti per l'SDK di Google.

        google_tools = []
        for tool in tools:
            # Convert JSON Schema to Google FunctionDeclaration. 
            tool_parameters = tool.get('inputSchema', {})
            
            # Map parameters to genai.protos.Schema format
            parameters_schema = genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={
                    k: genai.protos.Schema(type=genai.protos.Type[v['type'].upper()])
                    for k, v in tool_parameters.get('properties', {}).items()
                },
                required=tool_parameters.get('required', [])
            )

            google_tools.append(genai.protos.Tool(
                function_declarations=[genai.protos.FunctionDeclaration(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters=parameters_schema
                )]
            ))
            
        # 1. Extract system instruction and convert messages to Google Content format
        system_instruction = None
        history = []
        for msg in messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
                continue  # Don't add system message to history
            # Google Chat roles are 'user' and 'model'
            role = "user" if msg["role"] in ["user", "tool"] else "model"
            parts = []
            
            if msg["role"] == "tool":
                # Google expects FunctionResponse
                tool_name = msg.get("name")
                parts.append(genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=msg["name"],
                        response={"result": msg["content"]}
                    )
                ))
            elif msg["role"] == "assistant" and msg.get("tool_calls"):
                 # Google expects FunctionCall
                 for tc in msg["tool_calls"]:
                     
                     # RISOLUZIONE DEL PROBLEMA: CONVERSIONE OBBLIGATORIA A Protobuf Struct
                     proto_args = struct_pb2.Struct()
                     proto_args.update(tc["arguments"]) 
                     
                     parts.append(genai.protos.Part(
                         function_call=genai.protos.FunctionCall(
                             name=tc["name"],
                             args=proto_args # Ora è l'oggetto Protobuf
                         )
                     ))
            else:
                # Regular text message
                text_content = msg.get("content", "")
                if not text_content:
                    text_content = " " # Placeholder to prevent empty parts
                
                parts.append(genai.protos.Part(text=text_content))
                
            # Only add to history if we have parts
            if parts:
                current_content = genai.protos.Content(role=role, parts=parts)
                
                # MERGE LOGIC: If the last message in history has the same role, append parts to it
                if history and history[-1].role == role:
                    history[-1].parts.extend(parts)
                else:
                    history.append(current_content)

        # Re-initialize model with system instruction if present
        # This is lightweight and ensures the system prompt is respected
        if system_instruction:
            self.model = genai.GenerativeModel(
                self.model.model_name, 
                system_instruction=system_instruction,
                safety_settings=self.safety_settings
            )

        # Generate
        # We need to use the chat interface to maintain history correctly with tools
        
        # Split history into past turns and current turn
        # The last message in 'history' is the one we want to send now
        chat_history = history[:-1] if len(history) > 0 else []
        current_message = history[-1] if len(history) > 0 else None
        
        if not current_message:
             return {"content": "Error: No message content to send.", "tool_calls": None}

        chat = self.model.start_chat(history=chat_history)
        
        # The tools config must be passed with the send_message call
        try:
            response = chat.send_message(
                current_message,
                tools=google_tools,
                safety_settings=self.safety_settings
            )
        except Exception as e:
            # Catch "model output must contain either output text or tool calls" and other generation errors
            return {"content": f"I encountered an error generating a response: {str(e)}. Please try again.", "tool_calls": None}
        
        # 3. Decode the Google response
        tool_calls = []
        content_text = ""
        
        # Check for function calls and text in the response parts
        if response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content.parts:
                for part in candidate.content.parts:
                    # Safely extract text if present
                    try:
                        if hasattr(part, 'text') and part.text:
                            content_text += part.text
                    except (ValueError, AttributeError):
                        # Part doesn't have text, skip
                        pass
                    
                    # Check for function calls
                    if hasattr(part, 'function_call') and part.function_call:
                        # Convert Protobuf Struct arguments back to Python dict
                        tool_args = dict(part.function_call.args) 
                        
                        tool_calls.append({
                            "id": f"gemini_tc_{len(tool_calls) + 1}", 
                            "name": part.function_call.name,
                            "arguments": tool_args
                        })
        
        # Ensure we have at least some content
        if not content_text and not tool_calls:
            content_text = "I apologize, but I couldn't generate a proper response. Please try rephrasing your question."


        return {"content": content_text, "tool_calls": tool_calls if tool_calls else None}

def get_llm_provider(provider_name: str, api_key: str) -> LLMProvider:
    if provider_name.lower() == "openai":
        return OpenAIProvider(api_key)
    elif provider_name.lower() == "anthropic":
        return AnthropicProvider(api_key)
    elif provider_name.lower() == "google":
        return GoogleProvider(api_key)
    else:
        raise ValueError(f"Unknown provider: {provider_name}")
