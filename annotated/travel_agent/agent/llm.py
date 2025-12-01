import os  # Import the os module to interact with the operating system
from abc import ABC, abstractmethod  # Import ABC and abstractmethod for defining abstract base classes
from typing import List, Dict, Any, Optional  # Import type hinting utilities
import json  # Import the json module for JSON processing

# Import SDKs
try:  # Try to import the OpenAI SDK
    from openai import OpenAI  # Import the OpenAI class
except ImportError:  # Catch ImportError if the SDK is not installed
    OpenAI = None  # Set OpenAI to None if import fails

try:  # Try to import the Anthropic SDK
    from anthropic import Anthropic  # Import the Anthropic class
except ImportError:  # Catch ImportError if the SDK is not installed
    Anthropic = None  # Set Anthropic to None if import fails

try:  # Try to import the Google Generative AI SDK
    import google.generativeai as genai  # Import the genai module
    from google.protobuf import struct_pb2  # Import struct_pb2 for protobuf handling
except ImportError:  # Catch ImportError if the SDK is not installed
    genai = None  # Set genai to None if import fails

class LLMProvider(ABC):  # Define the abstract base class LLMProvider
    """Abstract base class for LLM providers."""  # Docstring for the class
    
    @abstractmethod  # Decorator to mark the method as abstract
    def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:  # Define the abstract generate_text method
        """Generate text from the LLM."""  # Docstring for the method
        pass  # Placeholder for abstract method implementation

    @abstractmethod  # Decorator to mark the method as abstract
    def call_tool(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:  # Define the abstract call_tool method
        """Generate a response that might include a tool call."""  # Docstring for the method
        pass  # Placeholder for abstract method implementation

class OpenAIProvider(LLMProvider):  # Define the OpenAIProvider class inheriting from LLMProvider
    def __init__(self, api_key: str, model: str = "gpt-4o"):  # Constructor for the class
        if not OpenAI:  # Check if OpenAI SDK is installed
            raise ImportError("OpenAI SDK not installed.")  # Raise error if not installed
        self.client = OpenAI(api_key=api_key)  # Initialize the OpenAI client with the API key
        self.model = model  # Set the model name

    def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:  # Implement generate_text method
        messages = []  # Initialize an empty list for messages
        if system_prompt:  # Check if a system prompt is provided
            messages.append({"role": "system", "content": system_prompt})  # Add the system prompt to messages
        messages.append({"role": "user", "content": prompt})  # Add the user prompt to messages
        
        response = self.client.chat.completions.create(  # Call the OpenAI API to generate a completion
            model=self.model,  # Specify the model
            messages=messages  # Pass the messages
        )
        return response.choices[0].message.content  # Return the content of the generated message

    def call_tool(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:  # Implement call_tool method
        # OpenAI expects strict role structure: system -> [user, assistant, tool]*
        # Our generic 'tool' role maps directly to OpenAI's 'tool' role
        
        openai_tools = []  # Initialize list for OpenAI tool definitions
        for tool in tools:  # Iterate through the provided tools
            openai_tools.append({  # Add tool definition to the list
                "type": "function",  # Specify type as function
                "function": {  # Define the function details
                    "name": tool["name"],  # Set function name
                    "description": tool.get("description", ""),  # Set function description
                    "parameters": tool.get("inputSchema", {})  # Set function parameters
                }
            })

        response = self.client.chat.completions.create(  # Call the OpenAI API
            model=self.model,  # Specify the model
            messages=messages,  # Pass the messages
            tools=openai_tools if openai_tools else None,  # Pass tools if available
            tool_choice="auto" if openai_tools else None  # Set tool_choice to auto if tools are available
        )
        
        message = response.choices[0].message  # Get the message from the response
        
        if message.tool_calls:  # Check if the model called any tools
            tool_calls = []  # Initialize list for tool calls
            for tc in message.tool_calls:  # Iterate through tool calls
                tool_calls.append({  # Add tool call details to the list
                    "id": tc.id,  # Set tool call ID
                    "name": tc.function.name,  # Set function name
                    "arguments": json.loads(tc.function.arguments)  # Parse and set arguments
                })
            return {"content": message.content, "tool_calls": tool_calls}  # Return content and tool calls
        
        return {"content": message.content, "tool_calls": None}  # Return content with no tool calls

class AnthropicProvider(LLMProvider):  # Define the AnthropicProvider class inheriting from LLMProvider
    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):  # Constructor for the class
        if not Anthropic:  # Check if Anthropic SDK is installed
            raise ImportError("Anthropic SDK not installed.")  # Raise error if not installed
        self.client = Anthropic(api_key=api_key)  # Initialize the Anthropic client
        self.model = model  # Set the model name

    def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:  # Implement generate_text method
        kwargs = {  # Initialize keyword arguments for the API call
            "model": self.model,  # Set the model
            "max_tokens": 1024,  # Set max tokens
            "messages": [{"role": "user", "content": prompt}]  # Set the user message
        }
        if system_prompt:  # Check if system prompt is provided
            kwargs["system"] = system_prompt  # Add system prompt to kwargs
            
        response = self.client.messages.create(**kwargs)  # Call the Anthropic API
        return response.content[0].text  # Return the generated text

    def call_tool(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:  # Implement call_tool method
        # Anthropic Tool Use Format:
        # User: ...
        # Assistant: <tool_use>...</tool_use>
        # User: <tool_result>...</tool_result>
        
        anthropic_tools = []  # Initialize list for Anthropic tool definitions
        for tool in tools:  # Iterate through provided tools
            anthropic_tools.append({  # Add tool definition
                "name": tool["name"],  # Set tool name
                "description": tool.get("description", ""),  # Set tool description
                "input_schema": tool.get("inputSchema", {})  # Set input schema
            })

        system_prompt = None  # Initialize system prompt variable
        converted_messages = []  # Initialize list for converted messages
        
        for msg in messages:  # Iterate through input messages
            if msg["role"] == "system":  # Check if message is system prompt
                system_prompt = msg["content"]  # Extract system prompt
            elif msg["role"] == "tool":  # Check if message is a tool result
                # Convert generic 'tool' role to Anthropic 'user' role with tool_result content
                converted_messages.append({  # Add converted message
                    "role": "user",  # Set role to user
                    "content": [{  # Set content as tool result block
                        "type": "tool_result",  # Set type
                        "tool_use_id": msg["tool_call_id"],  # Set tool use ID
                        "content": msg["content"]  # Set result content
                    }]
                })
            elif msg["role"] == "assistant" and "tool_calls" in msg:  # Check if message is assistant tool call
                # Need to reconstruct the assistant message with tool_use blocks
                content_blocks = []  # Initialize content blocks
                if msg.get("content"):  # Check if there is text content
                    content_blocks.append({"type": "text", "text": msg["content"]})  # Add text block
                
                if msg.get("tool_calls"):  # Check if there are tool calls
                    for tc in msg["tool_calls"]:  # Iterate through tool calls
                        content_blocks.append({  # Add tool use block
                            "type": "tool_use",  # Set type
                            "id": tc["id"],  # Set ID
                            "name": tc["name"],  # Set name
                            "input": tc["arguments"]  # Set input arguments
                        })
                
                converted_messages.append({  # Add converted assistant message
                    "role": "assistant",  # Set role
                    "content": content_blocks  # Set content blocks
                })
            else:  # For other message types (user, plain assistant)
                converted_messages.append(msg)  # Add message as is

        kwargs = {  # Initialize kwargs for API call
            "model": self.model,  # Set model
            "max_tokens": 1024,  # Set max tokens
            "messages": converted_messages,  # Set messages
            "tools": anthropic_tools  # Set tools
        }
        if system_prompt:  # Check if system prompt exists
            kwargs["system"] = system_prompt  # Add system prompt

        response = self.client.messages.create(**kwargs)  # Call Anthropic API
        
        tool_calls = []  # Initialize tool calls list
        content_text = ""  # Initialize content text
        
        for block in response.content:  # Iterate through response content blocks
            if block.type == "text":  # Check if block is text
                content_text += block.text  # Append text
            elif block.type == "tool_use":  # Check if block is tool use
                tool_calls.append({  # Add tool call details
                    "id": block.id,  # Set ID
                    "name": block.name,  # Set name
                    "arguments": block.input  # Set arguments
                })
                
        return {"content": content_text, "tool_calls": tool_calls if tool_calls else None}  # Return result

class GoogleProvider(LLMProvider):  # Define GoogleProvider class
    def __init__(self, api_key: str, model: str = "gemini-1.5-pro"):  # Constructor
        if not genai:  # Check if SDK installed
            raise ImportError("Google Generative AI SDK not installed.")  # Raise error
        genai.configure(api_key=api_key)  # Configure SDK with API key
        self.model = genai.GenerativeModel(model)  # Initialize model

    def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:  # Implement generate_text
        full_prompt = prompt  # Initialize full prompt
        if system_prompt:  # Check for system prompt
            full_prompt = f"System: {system_prompt}\nUser: {prompt}"  # Prepend system prompt
        response = self.model.generate_content(full_prompt)  # Generate content
        return response.text  # Return text

    def call_tool(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:  # Implement call_tool
        # Basic Google Tool Support
        # Note: This is a best-effort implementation. 
        # Google's SDK manages history via ChatSession usually, but here we have stateless messages.
        
        google_tools = []  # Initialize google tools list
        for tool in tools:  # Iterate through tools
            # Convert JSON Schema to Google FunctionDeclaration
            # This is complex to map perfectly, doing a simplified mapping
            google_tools.append({  # Add tool definition
                "function_declarations": [{  # Define function
                    "name": tool["name"],  # Set name
                    "description": tool.get("description", ""),  # Set description
                    "parameters": tool.get("inputSchema", {})  # Set parameters
                }]
            })
            
        # Convert messages to Google Content format
        history = []  # Initialize history list
        for msg in messages:  # Iterate through messages
            role = "user" if msg["role"] in ["user", "tool"] else "model"  # Map role to Google format
            parts = []  # Initialize parts list
            
            if msg["role"] == "tool":  # Check if tool result
                # Google expects FunctionResponse
                parts.append(genai.protos.Part(  # Add function response part
                    function_response=genai.protos.FunctionResponse(
                        name=msg["name"],  # Set function name
                        response={"result": msg["content"]}  # Set result
                    )
                ))
            elif msg["role"] == "assistant" and msg.get("tool_calls"):  # Check if assistant tool call
                 # Google expects FunctionCall
                 for tc in msg["tool_calls"]:  # Iterate tool calls
                     parts.append(genai.protos.Part(  # Add function call part
                         function_call=genai.protos.FunctionCall(
                             name=tc["name"],  # Set name
                             args=tc["arguments"]  # Set args
                         )
                     ))
            else:  # Normal text message
                parts.append(genai.protos.Part(text=msg.get("content", "")))  # Add text part
                
            history.append(genai.protos.Content(role=role, parts=parts))  # Add content to history

        # Generate
        # We need to use the chat interface to maintain history correctly with tools
        chat = self.model.start_chat(history=history[:-1] if history else [])  # Start chat with history
        last_msg = history[-1] if history else None  # Get last message
        
        # This is tricky because start_chat expects history, and we send the last message
        # But if the last message was a tool response, we need to send it carefully
        
        # Fallback: Just warn user
        return {"content": "Google Tool Calling requires complex protobuf mapping. Please use OpenAI or Anthropic for full tool support.", "tool_calls": None}  # Return warning

def get_llm_provider(provider_name: str, api_key: str) -> LLMProvider:  # Factory function to get provider
    if provider_name.lower() == "openai":  # Check if OpenAI
        return OpenAIProvider(api_key)  # Return OpenAI provider
    elif provider_name.lower() == "anthropic":  # Check if Anthropic
        return AnthropicProvider(api_key)  # Return Anthropic provider
    elif provider_name.lower() == "google":  # Check if Google
        return GoogleProvider(api_key)  # Return Google provider
    else:  # Unknown provider
        raise ValueError(f"Unknown provider: {provider_name}")  # Raise error
