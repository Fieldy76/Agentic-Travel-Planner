"""
================================================================================
LLM PROVIDERS - Multi-Provider LLM Abstraction Layer
================================================================================

This module provides a unified interface for multiple Large Language Model (LLM)
providers. It abstracts away the differences between OpenAI, Anthropic, and 
Google APIs, allowing the rest of the application to work with any provider
through a consistent interface.

Design Pattern: Factory + Strategy
-----------------------------------
- Factory Pattern: get_llm_provider() creates the appropriate provider instance
- Strategy Pattern: LLMProvider ABC defines the interface, concrete classes implement

Supported Providers:
--------------------
1. OpenAI (GPT-4o, GPT-4, GPT-3.5-turbo)
   - Uses the official openai Python SDK
   - Supports function calling natively
   
2. Anthropic (Claude 3.5 Sonnet, Claude 3 Opus)
   - Uses the official anthropic Python SDK  
   - Tool use via structured content blocks
   
3. Google (Gemini Pro, Gemini Flash)
   - Uses google-generativeai Python SDK
   - Function calling with protobuf definitions

Key Concepts:
-------------

Message Format (Unified):
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi!", "tool_calls": [...]},
        {"role": "tool", "tool_call_id": "123", "name": "func", "content": "result"}
    ]

Tool Call Response:
    {
        "content": "Optional text response",
        "tool_calls": [
            {"id": "tc_1", "name": "search_flights", "arguments": {...}},
            {"id": "tc_2", "name": "get_weather", "arguments": {...}}
        ]
    }

Provider-Specific Quirks:
-------------------------
- OpenAI: Uses "function" type for tools, arguments are JSON strings
- Anthropic: Uses tool_use/tool_result content blocks, requires non-empty blocks
- Google: Uses protobuf for function declarations, async via _async methods

Error Handling:
---------------
Each provider handles errors internally and raises appropriate exceptions.
The orchestrator should wrap calls in try/except for graceful degradation.

Author: Agentic Travel Planner Team
================================================================================
"""

# =============================================================================
# IMPORTS
# =============================================================================

import os                                        # Environment variable access
from abc import ABC, abstractmethod              # Abstract base class support
from typing import List, Dict, Any, Optional     # Type hints
import json                                      # JSON parsing for tool arguments

# =============================================================================
# CONDITIONAL SDK IMPORTS
# =============================================================================

# OpenAI SDK - Import with fallback to None if not installed
# This allows the module to load even if openai isn't installed,
# as long as the user doesn't try to use OpenAI provider.
try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

# Anthropic SDK - Same pattern
try:
    from anthropic import AsyncAnthropic
except ImportError:
    AsyncAnthropic = None

# Google Generative AI SDK - Same pattern
# Also imports struct_pb2 for protobuf handling of function arguments
try:
    import google.generativeai as genai
    from google.protobuf import struct_pb2
except ImportError:
    genai = None

# =============================================================================
# LANGFUSE OBSERVABILITY (Optional)
# =============================================================================
# Langfuse provides LLM observability, tracing, and analytics.
# It captures prompt/completion pairs, latency, token usage, and costs.
# If not configured (no API keys), tracing is silently disabled.

try:
    from langfuse.decorators import observe, langfuse_context
    from langfuse import Langfuse
    
    # Initialize Langfuse only if both keys are present
    _langfuse_secret = os.getenv("LANGFUSE_SECRET_KEY")
    _langfuse_public = os.getenv("LANGFUSE_PUBLIC_KEY")
    
    if _langfuse_secret and _langfuse_public:
        langfuse_client = Langfuse(
            secret_key=_langfuse_secret,
            public_key=_langfuse_public,
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        )
        LANGFUSE_ENABLED = True
    else:
        langfuse_client = None
        LANGFUSE_ENABLED = False
except ImportError:
    # Langfuse not installed - disable gracefully
    observe = None
    langfuse_context = None
    langfuse_client = None
    LANGFUSE_ENABLED = False


def langfuse_observe(name: str = None, as_type: str = None):
    """
    Decorator wrapper for Langfuse's @observe decorator.
    
    This wrapper provides graceful degradation - if Langfuse is not
    configured or not installed, it becomes a no-op and functions
    execute normally without any tracing overhead.
    
    Args:
        name: Name for the trace span (e.g., "openai-call-tool")
        as_type: Type of span - "generation" for LLM calls, None for others
    
    Returns:
        Decorator that wraps @observe when Langfuse is enabled, no-op otherwise.
    
    Example:
        @langfuse_observe(name="openai-generate-text", as_type="generation")
        async def generate_text(self, prompt: str) -> str:
            ...
    """
    def decorator(func):
        if LANGFUSE_ENABLED and observe:
            return observe(name=name, as_type=as_type)(func)
        return func
    return decorator

# =============================================================================
# ABSTRACT BASE CLASS
# =============================================================================

class LLMProvider(ABC):
    """
    Abstract base class defining the interface for LLM providers.
    
    All LLM providers must implement these methods to be usable by
    the AgentOrchestrator. This ensures consistent behavior regardless
    of which actual LLM is being used.
    
    The interface is designed around two main use cases:
    1. Simple text generation (generate_text)
    2. Tool-augmented generation (call_tool)
    
    Both methods are async to support non-blocking I/O with LLM APIs.
    """
    
    @abstractmethod
    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Generate a simple text response from the LLM.
        
        This is the basic completion method for when you just need
        a text response without tool calling capability.
        
        Args:
            prompt: The user's input/question
            system_prompt: Optional system instructions to guide the model
        
        Returns:
            str: The model's text response
        
        Note:
            This method is rarely used directly by the agent, which
            prefers call_tool for its tool-calling capabilities.
        """
        pass

    @abstractmethod
    async def call_tool(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate a response that may include tool calls.
        
        This is the primary method used by the AgentOrchestrator. It sends
        the conversation history and available tools to the LLM, which may
        respond with text, tool calls, or both.
        
        Args:
            messages: Conversation history in the unified message format.
                     Each message has 'role' and 'content', plus optional
                     'tool_calls' for assistant messages or 'tool_call_id'
                     for tool result messages.
            
            tools: List of tool definitions in JSON schema format.
                  Each tool has 'name', 'description', and 'inputSchema'.
        
        Returns:
            dict: Response with two fields:
                - content (str | None): Text response from the model
                - tool_calls (list | None): List of tool calls, each with
                  'id', 'name', and 'arguments' fields
        
        Example:
            >>> response = await provider.call_tool(messages, tools)
            >>> print(response)
            {
                "content": "I'll search for flights now.",
                "tool_calls": [{
                    "id": "tc_123",
                    "name": "search_flights",
                    "arguments": {"origin": "NYC", "destination": "LAX"}
                }]
            }
        """
        pass

# =============================================================================
# OPENAI PROVIDER
# =============================================================================

class OpenAIProvider(LLMProvider):
    """
    LLM provider implementation for OpenAI models (GPT-4, GPT-4o, etc.).
    
    This class uses the official OpenAI Python SDK in async mode.
    It maps the unified message format to OpenAI's API format and
    handles tool calling through OpenAI's function calling feature.
    
    Attributes:
        client (AsyncOpenAI): The async OpenAI client instance
        model (str): Model identifier (default: "gpt-4o")
    
    Model Options:
        - gpt-4o: Latest GPT-4 Omni model, best for complex reasoning
        - gpt-4-turbo: Fast GPT-4 variant
        - gpt-3.5-turbo: Faster, cheaper, less capable
    
    OpenAI Message Format:
        OpenAI uses a straightforward format that closely matches our unified format:
        - system: {"role": "system", "content": "..."}
        - user: {"role": "user", "content": "..."}
        - assistant: {"role": "assistant", "content": "...", "tool_calls": [...]}
        - tool: {"role": "tool", "tool_call_id": "...", "content": "..."}
    
    Tool Format (OpenAI):
        {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
    """
    
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        """
        Initialize the OpenAI provider.
        
        Args:
            api_key: OpenAI API key (starts with 'sk-')
            model: Model to use (default: "gpt-4o")
        
        Raises:
            ImportError: If the openai package is not installed
        """
        if not AsyncOpenAI:
            raise ImportError("OpenAI SDK not installed.")
        
        # Create async client with the provided API key
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    @langfuse_observe(name="openai-generate-text", as_type="generation")
    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text without tool calling capability."""
        # Build messages list
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # Call the chat completions endpoint
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )
        
        # Extract and return the text content
        return response.choices[0].message.content

    @langfuse_observe(name="openai-call-tool", as_type="generation")
    async def call_tool(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Call the OpenAI API with tool calling capability.
        
        OpenAI's function calling is straightforward - tools are defined
        in the request, and the model may respond with tool_calls in the
        message. Our unified format maps almost directly to OpenAI's format.
        
        Args:
            messages: Conversation history in unified format
            tools: Tool definitions from MCP Server
        
        Returns:
            dict: Response with 'content' and 'tool_calls' fields
        """
        # Convert tools to OpenAI's function format
        # OpenAI expects: {"type": "function", "function": {...}}
        openai_tools = []
        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {})  # JSON Schema format
                }
            })

        # Make the API call
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,  # OpenAI format matches our format closely
            tools=openai_tools if openai_tools else None,
            tool_choice="auto" if openai_tools else None  # Let model decide
        )
        
        # Extract the message from the response
        message = response.choices[0].message
        
        # Check if the model wants to call tools
        if message.tool_calls:
            tool_calls = []
            for tc in message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    # OpenAI returns arguments as a JSON string, parse it
                    "arguments": json.loads(tc.function.arguments)
                })
            return {"content": message.content, "tool_calls": tool_calls}
        
        # No tool calls, just return the text content
        return {"content": message.content, "tool_calls": None}

# =============================================================================
# ANTHROPIC PROVIDER
# =============================================================================

class AnthropicProvider(LLMProvider):
    """
    LLM provider implementation for Anthropic models (Claude).
    
    Anthropic's API has a different structure than OpenAI, particularly
    for tool use. This class handles the translation between our unified
    format and Anthropic's specific requirements.
    
    Attributes:
        client (AsyncAnthropic): The async Anthropic client instance
        model (str): Model identifier (default: "claude-3-5-sonnet-20241022")
    
    Model Options:
        - claude-3-5-sonnet-20241022: Latest Sonnet, best balance
        - claude-3-opus-20240229: Most capable, slower
        - claude-3-haiku-20240307: Fastest, less capable
    
    Anthropic Tool Use Format:
    --------------------------
    Anthropic uses a unique content block format for tool use:
    
    Assistant with tool_use:
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "I'll search for flights."},
                {"type": "tool_use", "id": "tc_1", "name": "search_flights", "input": {...}}
            ]
        }
    
    User with tool_result (note: it's under "user" role):
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "tc_1", "content": "..."}
            ]
        }
    
    Key Differences from OpenAI:
    - System prompt is a separate parameter, not a message
    - Tool results are sent as "user" role with tool_result content type
    - Empty content blocks are not allowed (important edge case!)
    """
    
    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        """
        Initialize the Anthropic provider.
        
        Args:
            api_key: Anthropic API key (starts with 'sk-ant-')
            model: Model to use (default: Claude 3.5 Sonnet)
        
        Raises:
            ImportError: If the anthropic package is not installed
        """
        if not AsyncAnthropic:
            raise ImportError("Anthropic SDK not installed.")
        
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model

    @langfuse_observe(name="anthropic-generate-text", as_type="generation")
    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text without tool calling capability."""
        kwargs = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        # Anthropic takes system prompt as a separate kwarg, not a message
        if system_prompt:
            kwargs["system"] = system_prompt
            
        response = await self.client.messages.create(**kwargs)
        return response.content[0].text

    @langfuse_observe(name="anthropic-call-tool", as_type="generation")
    async def call_tool(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Call the Anthropic API with tool use capability.
        
        This method handles the complex translation between our unified
        message format and Anthropic's specific format, especially for
        tool use and tool results.
        
        Conversion Required:
        1. Extract system prompt (it's a separate parameter)
        2. Convert "tool" role messages to "user" with tool_result content
        3. Convert assistant messages with tool_calls to content blocks
        4. Filter out empty content blocks (Anthropic doesn't allow them)
        
        Args:
            messages: Conversation history in unified format
            tools: Tool definitions from MCP Server
        
        Returns:
            dict: Response with 'content' and 'tool_calls' fields
        """
        # Convert tools to Anthropic's format
        # Anthropic uses input_schema instead of parameters
        anthropic_tools = []
        for tool in tools:
            anthropic_tools.append({
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get("inputSchema", {})  # Note: input_schema not parameters
            })

        # Extract system prompt and convert messages
        system_prompt = None
        converted_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                # System messages are handled separately in Anthropic
                system_prompt = msg["content"]
                
            elif msg["role"] == "tool":
                # Tool results must be sent as user role with tool_result content block
                # This is a key difference from OpenAI
                converted_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg["tool_call_id"],
                        "content": msg["content"]
                    }]
                })
                
            elif msg["role"] == "assistant" and "tool_calls" in msg:
                # Assistant messages with tool calls need to be converted
                # to content blocks with tool_use type
                content_blocks = []
                
                # Add text content if present
                if msg.get("content"):
                    content_blocks.append({"type": "text", "text": msg["content"]})
                
                # Add tool_use blocks for each tool call
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc["arguments"]  # Note: input not arguments
                        })
                
                # CRITICAL FIX: Anthropic does not allow empty content blocks
                # Skip the message entirely if there's no content
                if not content_blocks:
                    continue 

                converted_messages.append({
                    "role": "assistant",
                    "content": content_blocks
                })
                
            else:
                # Regular user/assistant messages
                # Skip empty messages to avoid API errors
                if not msg.get("content"):
                    continue
                converted_messages.append(msg)

        # Build the API request
        kwargs = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": converted_messages,
            "tools": anthropic_tools
        }
        
        if system_prompt:
            kwargs["system"] = system_prompt

        # Make the API call
        response = await self.client.messages.create(**kwargs)
        
        # Parse the response
        tool_calls = []
        content_text = ""
        
        # Anthropic returns content as a list of blocks
        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                # Extract tool call information
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input  # Note: input not arguments
                })
                
        return {"content": content_text, "tool_calls": tool_calls if tool_calls else None}

# =============================================================================
# GOOGLE PROVIDER
# =============================================================================

class GoogleProvider(LLMProvider):
    """
    LLM provider implementation for Google's Gemini models.
    
    Google's Generative AI SDK has a unique approach using protobuf
    definitions for function calling. This class handles the translation
    between our unified format and Google's specific requirements.
    
    Attributes:
        model (GenerativeModel): The Gemini model instance
        safety_settings (dict): Content safety configuration
    
    Model Options:
        - gemini-2.0-flash: Fast, capable (default)
        - gemini-1.5-pro: Most capable Gemini model
        - gemini-1.5-flash: Balanced speed and capability
    
    Google's Function Calling:
    --------------------------
    Google uses Protocol Buffers (protobuf) for function definitions:
    
    FunctionDeclaration:
        genai.protos.FunctionDeclaration(
            name="search_flights",
            description="Search for flights",
            parameters=genai.protos.Schema(
                type=Type.OBJECT,
                properties={...},
                required=[...]
            )
        )
    
    Key Differences:
    - Uses protobuf Schema instead of JSON Schema
    - Chat history through start_chat() with history
    - Function responses use FunctionResponse protobuf
    - Async via _async suffix methods
    - Safety settings are required to avoid content filtering
    """
    
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        """
        Initialize the Google Gemini provider.
        
        Args:
            api_key: Google API key
            model: Model to use (default: "gemini-2.0-flash")
        
        Raises:
            ImportError: If google-generativeai is not installed
        """
        if not genai:
            raise ImportError("Google Generative AI SDK not installed.")
        
        # Configure the SDK with the API key globally
        genai.configure(api_key=api_key)
        
        # Safety settings to minimize content filtering
        # Set to BLOCK_NONE for all categories to avoid blocking agent responses
        # In production, you might want more restrictive settings
        self.safety_settings = {
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
        }
        
        # Create the model instance
        self.model = genai.GenerativeModel(model)

    @langfuse_observe(name="google-generate-text", as_type="generation")
    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text without function calling capability."""
        # Combine system prompt with user prompt if provided
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"System: {system_prompt}\nUser: {prompt}"
        
        # Use async generation method
        response = await self.model.generate_content_async(full_prompt)
        return response.text

    @langfuse_observe(name="google-call-tool", as_type="generation")
    async def call_tool(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Call the Google Gemini API with function calling capability.
        
        This method handles the complex translation between our unified
        format and Google's protobuf-based format. The key challenges are:
        
        1. Converting JSON Schema to Google's protobuf Schema
        2. Converting message history to Google's Content format
        3. Handling function calls and responses with protobuf
        4. Managing the chat session correctly
        
        Args:
            messages: Conversation history in unified format
            tools: Tool definitions from MCP Server
        
        Returns:
            dict: Response with 'content' and 'tool_calls' fields
        """
        # =====================================================================
        # Step 1: Convert tools to Google's protobuf format
        # =====================================================================
        google_tools = []
        for tool in tools:
            # Get the input schema from the tool definition
            tool_parameters = tool.get('inputSchema', {})
            
            # Convert JSON Schema properties to Google's protobuf Schema
            # This maps basic types: string -> STRING, integer -> INTEGER, etc.
            parameters_schema = genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={
                    k: genai.protos.Schema(type=genai.protos.Type[v['type'].upper()])
                    for k, v in tool_parameters.get('properties', {}).items()
                },
                required=tool_parameters.get('required', [])
            )

            # Create a Tool proto with the FunctionDeclaration
            google_tools.append(genai.protos.Tool(
                function_declarations=[genai.protos.FunctionDeclaration(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters=parameters_schema
                )]
            ))
        
        # =====================================================================
        # Step 2: Convert messages to Google's Content format
        # =====================================================================
        system_instruction = None
        history = []
        
        for msg in messages:
            if msg["role"] == "system":
                # System instructions are handled separately
                system_instruction = msg["content"]
                continue
            
            # Google uses "user" and "model" roles (not "assistant")
            role = "user" if msg["role"] in ["user", "tool"] else "model"
            parts = []
            
            if msg["role"] == "tool":
                # Tool results are sent as FunctionResponse protos
                parts.append(genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=msg["name"],
                        response={"result": msg["content"]}
                    )
                ))
                
            elif msg["role"] == "assistant" and msg.get("tool_calls"):
                # Assistant messages with tool calls become FunctionCall protos
                for tc in msg["tool_calls"]:
                    # Convert arguments dict to protobuf Struct
                    proto_args = struct_pb2.Struct()
                    proto_args.update(tc["arguments"]) 
                    
                    parts.append(genai.protos.Part(
                        function_call=genai.protos.FunctionCall(
                            name=tc["name"],
                            args=proto_args
                        )
                    ))
            else:
                # Regular text messages
                # Handle file attachments (images, etc.)
                if msg.get("files"):
                    for file in msg["files"]:
                        parts.append(genai.protos.Part(
                            inline_data=genai.protos.Blob(
                                mime_type=file["mime_type"],
                                data=file["data"]
                            )
                        ))

                text_content = msg.get("content", "")
                # Ensure at least some content parts exist (Google requires non-empty)
                if not text_content and not parts: 
                    text_content = " "  # Minimal content to avoid errors
                
                if text_content:
                    parts.append(genai.protos.Part(text=text_content))
            
            # Add to history, merging consecutive same-role messages
            # (Google requires alternating user/model turns)
            if parts:
                current_content = genai.protos.Content(role=role, parts=parts)
                if history and history[-1].role == role:
                    # Merge with previous message of same role
                    history[-1].parts.extend(parts)
                else:
                    history.append(current_content)

        # =====================================================================
        # Step 3: Apply system instruction if present
        # =====================================================================
        if system_instruction:
            self.model = genai.GenerativeModel(
                self.model.model_name, 
                system_instruction=system_instruction,
                safety_settings=self.safety_settings
            )

        # =====================================================================
        # Step 4: Start chat and send message
        # =====================================================================
        # Split history into previous turns and current message
        chat_history = history[:-1] if len(history) > 0 else []
        current_message = history[-1] if len(history) > 0 else None
        
        if not current_message:
            return {"content": "Error: No message content to send.", "tool_calls": None}

        # Create chat session with history
        chat = self.model.start_chat(history=chat_history)
        
        try:
            # Send message asynchronously
            response = await chat.send_message_async(
                current_message,
                tools=google_tools,
                safety_settings=self.safety_settings
            )
        except Exception as e:
            # Handle any API errors gracefully
            print(f"CRITICAL GEMINI ERROR: {e}")
            import traceback
            traceback.print_exc()
            return {"content": f"I encountered an error generating a response: {str(e)}. Please try again.", "tool_calls": None}
        
        # =====================================================================
        # Step 5: Parse response
        # =====================================================================
        tool_calls = []
        content_text = ""
        
        # Check if we have valid candidates in the response
        if response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content.parts:
                for part in candidate.content.parts:
                    # Extract text content
                    try:
                        if hasattr(part, 'text') and part.text:
                            content_text += part.text
                    except (ValueError, AttributeError):
                        pass  # Some parts don't have text
                    
                    # Extract function calls
                    if hasattr(part, 'function_call') and part.function_call:
                        # Convert protobuf args back to dict
                        tool_args = dict(part.function_call.args) 
                        
                        tool_calls.append({
                            "id": f"gemini_tc_{len(tool_calls) + 1}",  # Generate ID
                            "name": part.function_call.name,
                            "arguments": tool_args
                        })
        
        # Handle empty response case
        if not content_text and not tool_calls:
            content_text = "I apologize, but I couldn't generate a proper response. Please try rephrasing your question."

        return {"content": content_text, "tool_calls": tool_calls if tool_calls else None}

# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def get_llm_provider(provider_name: str, api_key: str) -> LLMProvider:
    """
    Factory function to create the appropriate LLM provider.
    
    This function implements the Factory pattern, creating and returning
    the correct provider instance based on the provider name. It centralizes
    provider instantiation logic and handles unknown provider names.
    
    Args:
        provider_name: Name of the provider ("openai", "anthropic", or "google")
        api_key: API key for the specified provider
    
    Returns:
        LLMProvider: An instance of the appropriate provider class
    
    Raises:
        ValueError: If provider_name is not recognized
        ImportError: If the provider's SDK is not installed
    
    Example:
        >>> llm = get_llm_provider("openai", "sk-...")
        >>> response = await llm.generate_text("Hello!")
        
        >>> llm = get_llm_provider("anthropic", "sk-ant-...")
        >>> response = await llm.call_tool(messages, tools)
    """
    if provider_name.lower() == "openai":
        return OpenAIProvider(api_key)
    elif provider_name.lower() == "anthropic":
        return AnthropicProvider(api_key)
    elif provider_name.lower() == "google":
        return GoogleProvider(api_key)
    else:
        raise ValueError(f"Unknown provider: {provider_name}")
