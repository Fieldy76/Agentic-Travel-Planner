import os
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import json
from pathlib import Path
import traceback

# Load .env file to ensure environment variables are available
from dotenv import load_dotenv
_project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_project_root / ".env")
print(f"DEBUG: Loaded .env from {_project_root / '.env'}")
print(f"DEBUG: LANGFUSE_SECRET_KEY present: {bool(os.getenv('LANGFUSE_SECRET_KEY'))}")
print(f"DEBUG: LANGFUSE_PUBLIC_KEY present: {bool(os.getenv('LANGFUSE_PUBLIC_KEY'))}")

# Import SDKs
try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

try:
    from anthropic import AsyncAnthropic
except ImportError:
    AsyncAnthropic = None

try:
    import google.generativeai as genai
    from google.protobuf import struct_pb2
except ImportError:
    genai = None

# Langfuse Observability
# We wrap this in a try/except block to prevent the server from crashing
# if the library version is incompatible.
try:
    from langfuse import Langfuse
    
    _langfuse_secret = os.getenv("LANGFUSE_SECRET_KEY")
    _langfuse_public = os.getenv("LANGFUSE_PUBLIC_KEY")
    
    if _langfuse_secret and _langfuse_public:
        langfuse_client = Langfuse(
            secret_key=_langfuse_secret,
            public_key=_langfuse_public,
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        )
        LANGFUSE_ENABLED = True
        print("DEBUG: Langfuse initialized successfully")
    else:
        print("DEBUG: Langfuse keys missing - disabled")
        langfuse_client = None
        LANGFUSE_ENABLED = False
except (ImportError, Exception) as e:
    print(f"WARNING: Langfuse initialization failed: {e}")
    langfuse_client = None
    LANGFUSE_ENABLED = False


def langfuse_trace(name: str, user_id: str = None, session_id: str = None, metadata: dict = None):
    """Create a new Langfuse trace. Returns trace object or None if disabled/failed."""
    if LANGFUSE_ENABLED and langfuse_client:
        try:
            # Check if the trace method exists before calling it
            # v3 SDK uses start_span or similar
            if hasattr(langfuse_client, 'trace'):
                 return langfuse_client.trace(
                     name=name,
                     user_id=user_id,
                     session_id=session_id,
                     metadata=metadata or {}
                 )
            elif hasattr(langfuse_client, 'start_span'):
                # v3: start_span creates a span (potentially root)
                return langfuse_client.start_span(
                    name=name,
                    user_id=user_id,
                    session_id=session_id,
                    metadata=metadata or {}
                )
            else:
                print("WARNING: Langfuse client API unknown. Check library version.")
                return None
        except Exception as e:
            print(f"WARNING: Failed to create Langfuse trace: {e}")
            return None
    return None


def langfuse_generation(trace, name: str, model: str, input_data: Any, output_data: Any = None, metadata: dict = None):
    """Log a generation (LLM call) to an existing trace. Returns generation object or None."""
    # We check if trace is valid before attempting to log
    if trace and LANGFUSE_ENABLED:
        try:
            gen = None
            if hasattr(trace, 'generation'):
                gen = trace.generation(
                    name=name,
                    model=model,
                    input=input_data,
                    output=output_data,
                    metadata=metadata or {}
                )
            elif hasattr(trace, 'start_generation'):
                # v3: start_generation returns a generation object which we should end
                gen = trace.start_generation(
                    name=name,
                    model=model,
                    input=input_data,
                    output=output_data,
                    metadata=metadata or {}
                )
                if hasattr(gen, 'end'):
                    gen.end()
            return gen
        except Exception as e:
            print(f"WARNING: Failed to log generation to Langfuse: {e}")
            return None
    return None


def langfuse_flush():
    """Flush all pending Langfuse events to the server."""
    if LANGFUSE_ENABLED and langfuse_client:
        try:
            langfuse_client.flush()
        except Exception as e:
            print(f"WARNING: Langfuse flush failed: {e}")

class LLMProvider(ABC):
    """Abstract base class for LLM providers (Async)."""
    
    @abstractmethod
    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text from the LLM."""
        pass

    @abstractmethod
    async def call_tool(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate a response that might include a tool call."""
        pass

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        if not AsyncOpenAI:
            raise ImportError("OpenAI SDK not installed.")
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )
        return response.choices[0].message.content

    async def call_tool(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
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

        response = await self.client.chat.completions.create(
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
        if not AsyncAnthropic:
            raise ImportError("Anthropic SDK not installed.")
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model

    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        kwargs = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}]
        }
        if system_prompt:
            kwargs["system"] = system_prompt
            
        response = await self.client.messages.create(**kwargs)
        return response.content[0].text

    async def call_tool(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
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
                converted_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg["tool_call_id"],
                        "content": msg["content"]
                    }]
                })
            elif msg["role"] == "assistant" and "tool_calls" in msg:
                content_blocks = []
                if msg.get("content"):
                    content_blocks.append({"type": "text", "text": msg["content"]})
                
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc["arguments"]
                        })
                
                if not content_blocks:
                    continue 

                converted_messages.append({
                    "role": "assistant",
                    "content": content_blocks
                })
            else:
                if not msg.get("content"):
                    continue
                converted_messages.append(msg)

        kwargs = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": converted_messages,
            "tools": anthropic_tools
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = await self.client.messages.create(**kwargs)
        
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
        
        self.safety_settings = {
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
        }
        
        self.model = genai.GenerativeModel(model)

    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"System: {system_prompt}\nUser: {prompt}"
        response = await self.model.generate_content_async(full_prompt)
        return response.text

    async def call_tool(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        google_tools = []
        for tool in tools:
            tool_parameters = tool.get('inputSchema', {})
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
            
        system_instruction = None
        history = []
        for msg in messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
                continue
            role = "user" if msg["role"] in ["user", "tool"] else "model"
            parts = []
            
            if msg["role"] == "tool":
                parts.append(genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=msg["name"],
                        response={"result": msg["content"]}
                    )
                ))
            elif msg["role"] == "assistant" and msg.get("tool_calls"):
                 for tc in msg["tool_calls"]:
                     proto_args = struct_pb2.Struct()
                     proto_args.update(tc["arguments"]) 
                     
                     parts.append(genai.protos.Part(
                         function_call=genai.protos.FunctionCall(
                             name=tc["name"],
                             args=proto_args
                         )
                     ))
            else:
                if msg.get("files"):
                    for file in msg["files"]:
                        parts.append(genai.protos.Part(
                            inline_data=genai.protos.Blob(
                                mime_type=file["mime_type"],
                                data=file["data"]
                            )
                        ))

                text_content = msg.get("content", "")
                if not text_content and not parts: 
                    text_content = " "
                
                if text_content:
                    parts.append(genai.protos.Part(text=text_content))
                
            if parts:
                current_content = genai.protos.Content(role=role, parts=parts)
                if history and history[-1].role == role:
                    history[-1].parts.extend(parts)
                else:
                    history.append(current_content)

        if system_instruction:
            self.model = genai.GenerativeModel(
                self.model.model_name, 
                system_instruction=system_instruction,
                safety_settings=self.safety_settings
            )

        chat_history = history[:-1] if len(history) > 0 else []
        current_message = history[-1] if len(history) > 0 else None
        
        if not current_message:
             return {"content": "Error: No message content to send.", "tool_calls": None}

        chat = self.model.start_chat(history=chat_history)
        
        try:
            response = await chat.send_message_async(
                current_message,
                tools=google_tools,
                safety_settings=self.safety_settings
            )
        except Exception as e:
            print(f"CRITICAL GEMINI ERROR: {e}")
            traceback.print_exc()
            return {"content": f"I encountered an error generating a response: {str(e)}. Please try again.", "tool_calls": None}
        
        tool_calls = []
        content_text = ""
        
        if response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content.parts:
                for part in candidate.content.parts:
                    try:
                        if hasattr(part, 'text') and part.text:
                            content_text += part.text
                    except (ValueError, AttributeError):
                        pass
                    
                    if hasattr(part, 'function_call') and part.function_call:
                        tool_args = dict(part.function_call.args) 
                        
                        tool_calls.append({
                            "id": f"gemini_tc_{len(tool_calls) + 1}", 
                            "name": part.function_call.name,
                            "arguments": tool_args
                        })
        
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
