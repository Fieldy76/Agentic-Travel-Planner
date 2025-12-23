import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load .env
env_path = Path('.').resolve() / '.env'
print(f"Loading .env from: {env_path}")
load_dotenv(env_path)

# Check keys
secret_key = os.getenv("LANGFUSE_SECRET_KEY")
public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

print("-" * 50)
print(f"LANGFUSE_SECRET_KEY: {'[PRESENT]' if secret_key else '[MISSING]'}")
print(f"LANGFUSE_PUBLIC_KEY: {'[PRESENT]' if public_key else '[MISSING]'}")
print(f"LANGFUSE_HOST:       {host}")
print("-" * 50)

if not secret_key or not public_key:
    print("ERROR: Missing API keys in .env")
    sys.exit(1)

try:
    print("Importing Langfuse...")
    from langfuse import Langfuse
    
    print("Initializing Client...")
    langfuse = Langfuse(
        secret_key=secret_key,
        public_key=public_key,
        host=host,
        debug=True  # Enable debug mode
    )
    
    print("Creating verification trace (Root Span)...")
    # v3: trace() is removed, use start_span() or observation()
    # We use start_span which acts as a root trace if no parent context
    trace = langfuse.trace(name="verification_trace") if hasattr(langfuse, "trace") else langfuse.start_span(name="verification_trace")
    
    print("Adding generation...")
    # v3: use start_generation() and then end()
    if hasattr(trace, "generation"):
        trace.generation(
            name="verification_gen",
            model="test-model",
            input="Ping",
            output="Pong"
        )
    else:
        gen = trace.start_generation(
            name="verification_gen",
            model="test-model",
            input="Ping",
            output="Pong"
        )
        gen.end()
    
    trace.end() # Important: End the trace/span
    
    print("Flushing events to Langfuse...")
    start_time = os.times().elapsed
    langfuse.flush()
    end_time = os.times().elapsed
    
    print(f"Flush completed in {end_time - start_time:.2f} seconds.")
    print("\nSUCCESS! Check your Langfuse dashboard for 'verification_trace'.")
    print("If you don't see it:")
    print("1. Check if you are in the correct Project in Langfuse")
    print("2. Check if your LANGFUSE_HOST is correct (US vs EU)")
    print("   - EU (Default): https://cloud.langfuse.com")
    print("   - US:           https://us.cloud.langfuse.com")
    
except ImportError:
    print("ERROR: 'langfuse' package not installed. Run 'pip install langfuse'")
except Exception as e:
    print(f"\nCRITICAL ERROR: {e}")
    import traceback
    traceback.print_exc()
