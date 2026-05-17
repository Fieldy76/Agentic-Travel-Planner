import logging
import os
import traceback
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import json

# Importing Config triggers .env loading at module init; needed before we
# read LANGFUSE_* below.
from ..config import Config  # noqa: F401

logger = logging.getLogger(__name__)

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

try:
    from langfuse import Langfuse

    _langfuse_secret = os.getenv("LANGFUSE_SECRET_KEY")
    _langfuse_public = os.getenv("LANGFUSE_PUBLIC_KEY")

    if _langfuse_secret and _langfuse_public:
        langfuse_client = Langfuse(
            secret_key=_langfuse_secret,
            public_key=_langfuse_public,
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
        LANGFUSE_ENABLED = True
        logger.info("Langfuse initialized")
    else:
        langfuse_client = None
        LANGFUSE_ENABLED = False
        logger.info("Langfuse disabled (no keys set)")
except Exception as _e:
    logger.warning("Langfuse initialization failed: %s", _e)
    langfuse_client = None
    LANGFUSE_ENABLED = False


def langfuse_trace(name: str, user_id: str | None = None, session_id: str | None = None, metadata: dict | None = None):
    """Create a new Langfuse trace. Returns trace object or None if disabled/failed."""
    if not (LANGFUSE_ENABLED and langfuse_client):
        return None
    meta = dict(metadata or {})
    if user_id is not None:
        meta.setdefault("user_id", user_id)
    if session_id is not None:
        meta.setdefault("session_id", session_id)
    try:
        if hasattr(langfuse_client, "trace"):
            # v2 API
            return langfuse_client.trace(name=name, user_id=user_id, session_id=session_id, metadata=meta)
        if hasattr(langfuse_client, "start_span"):
            # v3 API — span doesn't take user/session kwargs; metadata is the channel.
            return langfuse_client.start_span(name=name, metadata=meta)
        logger.warning("Langfuse client API unknown; check library version")
    except Exception:
        logger.exception("Langfuse trace creation failed")
    return None


def langfuse_generation(trace, name: str, model: str, input_data: Any, output_data: Any = None, metadata: dict | None = None):
    """Log a generation (LLM call) to an existing trace."""
    if not (trace and LANGFUSE_ENABLED):
        return None
    try:
        if hasattr(trace, "generation"):
            # v2
            return trace.generation(name=name, model=model, input=input_data, output=output_data, metadata=metadata or {})
        if hasattr(trace, "start_observation"):
            # v3+: start_observation supersedes start_generation
            gen = trace.start_observation(
                as_type="generation", name=name, model=model,
                input=input_data, output=output_data, metadata=metadata or {},
            )
        elif hasattr(trace, "start_generation"):
            # v3 legacy
            gen = trace.start_generation(
                name=name, model=model, input=input_data,
                output=output_data, metadata=metadata or {},
            )
        else:
            return None
        if hasattr(gen, "end"):
            gen.end()
        return gen
    except Exception:
        logger.exception("Langfuse generation log failed")
    return None


def langfuse_flush():
    """Flush all pending Langfuse events to the server."""
    if LANGFUSE_ENABLED and langfuse_client:
        try:
            langfuse_client.flush()
        except Exception:
            logger.exception("Langfuse flush failed")

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
                try:
                    arguments = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError) as e:
                    # Surface as a tool call with an error payload so the agent loop
                    # can return the error to the LLM rather than crashing.
                    arguments = {"__error__": f"Malformed JSON arguments from LLM: {e}"}
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": arguments,
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
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        if not genai:
            raise ImportError("Google Generative AI SDK not installed.")
        genai.configure(api_key=api_key)

        self.safety_settings = {
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
        }

        self.model_name = model
        self.model = genai.GenerativeModel(model)
        # Cache rebuilt GenerativeModel instances per system_instruction so we
        # don't allocate a fresh client object on every call_tool().
        self._model_cache: Dict[str, Any] = {"": self.model}

    def _model_for(self, system_instruction: str | None):
        key = system_instruction or ""
        cached = self._model_cache.get(key)
        if cached is not None:
            return cached
        m = genai.GenerativeModel(
            self.model_name,
            system_instruction=system_instruction,
            safety_settings=self.safety_settings,
        )
        self._model_cache[key] = m
        return m

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
            properties = {}
            for k, v in tool_parameters.get('properties', {}).items():
                raw_type = (v.get('type') or 'string').upper()
                try:
                    proto_type = genai.protos.Type[raw_type]
                except KeyError:
                    proto_type = genai.protos.Type.STRING
                properties[k] = genai.protos.Schema(type=proto_type)
            parameters_schema = genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties=properties,
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

        active_model = self._model_for(system_instruction)

        chat_history = history[:-1] if len(history) > 0 else []
        current_message = history[-1] if len(history) > 0 else None

        if not current_message:
            return {"content": "Error: No message content to send.", "tool_calls": None}

        chat = active_model.start_chat(history=chat_history)

        try:
            response = await chat.send_message_async(
                current_message,
                tools=google_tools,
                safety_settings=self.safety_settings,
            )
        except Exception:
            logger.exception("Gemini call failed")
            return {
                "content": "I encountered an error generating a response. Please try again.",
                "tool_calls": None,
            }
        
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
