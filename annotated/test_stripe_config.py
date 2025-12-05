#!/usr/bin/env python3
"""
================================================================================
STRIPE CONFIGURATION TEST - Verify Stripe API Setup
================================================================================

This script tests the Stripe API configuration to ensure payment processing
is properly set up. Run this before deploying to verify:

1. Environment variables are correctly set
2. Stripe SDK is installed
3. API key is valid
4. Connection to Stripe API works

Usage:
------
    # From the project root directory:
    python test_stripe_config.py
    
    # Or with the virtual environment:
    source venv/bin/activate
    python test_stripe_config.py

Expected Output (Success):
--------------------------
    ===========================================================
    Stripe Configuration Test
    ===========================================================
    
    🔍 Testing Stripe Configuration...
    
    ✅ STRIPE_SECRET_KEY found: sk_test_1234...
    ✅ STRIPE_PUBLISHABLE_KEY found: pk_test_1234...
    ✅ Stripe SDK installed (version 8.0.0)
    ✅ Stripe API key set successfully
    
    🔄 Testing API connection...
    ✅ Stripe API connection successful!
       Account mode: TEST
       Available balance: 0.00 USD
    
    ===========================================================
    ✅ All tests passed! Your Stripe integration is ready.
    
    You can now:
      1. Start the server: python web_server.py
      2. Book a flight in the web UI
      3. Payment will be processed via Stripe
    
    Test card: 4242 4242 4242 4242
    ===========================================================

Error Cases:
------------
- Missing API keys: Check .env file
- Invalid API key: Verify key in Stripe Dashboard
- SDK not installed: pip install stripe>=8.0.0

Author: Agentic Travel Planner Team
================================================================================
"""

# =============================================================================
# IMPORTS
# =============================================================================

import os                          # Environment variable access
import sys                         # Exit codes
from dotenv import load_dotenv     # Load .env file

# =============================================================================
# ENVIRONMENT LOADING
# =============================================================================

# Load environment variables from .env file
# This should contain STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY
load_dotenv()

# =============================================================================
# TEST FUNCTION
# =============================================================================

def test_stripe_config():
    """
    Test Stripe configuration step by step.
    
    This function performs a series of checks to verify Stripe is
    properly configured:
    
    1. Check for API keys in environment
    2. Verify Stripe SDK is installed
    3. Test API key validity with a read-only API call
    
    Returns:
        bool: True if all tests pass, False otherwise
    """
    print("🔍 Testing Stripe Configuration...\n")
    
    # =========================================================================
    # Step 1: Check for API Keys
    # =========================================================================
    
    secret_key = os.getenv("STRIPE_SECRET_KEY")
    publishable_key = os.getenv("STRIPE_PUBLISHABLE_KEY")
    
    # Check secret key (required for server-side operations)
    if not secret_key:
        print("❌ STRIPE_SECRET_KEY not found in .env file")
        return False
    
    # Check publishable key (required for client-side if using Stripe.js)
    if not publishable_key:
        print("❌ STRIPE_PUBLISHABLE_KEY not found in .env file")
        return False
    
    # Show partial keys for verification (never show full key!)
    print(f"✅ STRIPE_SECRET_KEY found: {secret_key[:12]}...")
    print(f"✅ STRIPE_PUBLISHABLE_KEY found: {publishable_key[:12]}...")
    
    # =========================================================================
    # Step 2: Check Stripe SDK Installation
    # =========================================================================
    
    try:
        import stripe
        
        # Try to get version (API changed between versions)
        try:
            version = stripe.VERSION if hasattr(stripe, 'VERSION') else getattr(stripe, '_version', 'unknown')
        except:
            version = 'installed'
        
        print(f"✅ Stripe SDK installed (version {version})")
        
    except ImportError:
        print("❌ Stripe SDK not installed. Run: pip install stripe>=8.0.0")
        return False
    
    # =========================================================================
    # Step 3: Set API Key
    # =========================================================================
    
    try:
        stripe.api_key = secret_key
        print("✅ Stripe API key set successfully")
    except Exception as e:
        print(f"❌ Error setting Stripe API key: {e}")
        return False
    
    # =========================================================================
    # Step 4: Test API Connection
    # =========================================================================
    # Use Balance.retrieve() which is a read-only operation
    # that doesn't create any resources
    
    try:
        print("\n🔄 Testing API connection...")
        
        # Retrieve account balance - safe read-only operation
        balance = stripe.Balance.retrieve()
        
        print(f"✅ Stripe API connection successful!")
        
        # Show account mode (test vs live)
        if secret_key.startswith('sk_test'):
            print(f"   Account mode: TEST")
        else:
            print(f"   Account mode: LIVE")
        
        # Show available balance
        if balance.available and len(balance.available) > 0:
            amount = balance.available[0].amount / 100
            currency = balance.available[0].currency.upper()
            print(f"   Available balance: {amount:.2f} {currency}")
        
        return True
        
    except stripe.error.AuthenticationError:
        print("❌ Authentication failed - Invalid API key")
        print("   Please check your Stripe API keys in .env file")
        return False
        
    except stripe.error.StripeError as e:
        print(f"❌ Stripe API error: {e}")
        return False
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    # Print header
    print("=" * 60)
    print("Stripe Configuration Test")
    print("=" * 60 + "\n")
    
    # Run tests
    success = test_stripe_config()
    
    # Print footer with results
    print("\n" + "=" * 60)
    
    if success:
        print("✅ All tests passed! Your Stripe integration is ready.")
        print("\nYou can now:")
        print("  1. Start the server: python web_server.py")
        print("  2. Book a flight in the web UI")
        print("  3. Payment will be processed via Stripe")
        print("\nTest card: 4242 4242 4242 4242")
        print("=" * 60)
        sys.exit(0)  # Success exit code
    else:
        print("❌ Configuration issues found. Please fix them and try again.")
        print("=" * 60)
        sys.exit(1)  # Error exit code
