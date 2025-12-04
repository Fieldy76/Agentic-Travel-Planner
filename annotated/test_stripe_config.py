#!/usr/bin/env python3
"""
Quick test to verify Stripe API keys are configured correctly.
Run this to check if your Stripe integration is working.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_stripe_config():
    """Test Stripe configuration."""
    print("🔍 Testing Stripe Configuration...\n")
    
    # Check for Stripe keys
    secret_key = os.getenv("STRIPE_SECRET_KEY")
    publishable_key = os.getenv("STRIPE_PUBLISHABLE_KEY")
    
    if not secret_key:
        print("❌ STRIPE_SECRET_KEY not found in .env file")
        return False
    
    if not publishable_key:
        print("❌ STRIPE_PUBLISHABLE_KEY not found in .env file")
        return False
    
    print(f"✅ STRIPE_SECRET_KEY found: {secret_key[:12]}...")
    print(f"✅ STRIPE_PUBLISHABLE_KEY found: {publishable_key[:12]}...")
    
    # Check if Stripe SDK is installed
    try:
        import stripe
        # Get version safely
        try:
            version = stripe.VERSION if hasattr(stripe, 'VERSION') else getattr(stripe, '_version', 'unknown')
        except:
            version = 'installed'
        print(f"✅ Stripe SDK installed (version {version})")
    except ImportError:
        print("❌ Stripe SDK not installed. Run: pip install stripe>=8.0.0")
        return False
    
    # Try to initialize Stripe
    try:
        stripe.api_key = secret_key
        print("✅ Stripe API key set successfully")
    except Exception as e:
        print(f"❌ Error setting Stripe API key: {e}")
        return False
    
    # Try a simple API call to verify credentials
    try:
        print("\n🔄 Testing API connection...")
        # This is a safe read-only call that doesn't create anything
        balance = stripe.Balance.retrieve()
        print(f"✅ Stripe API connection successful!")
        print(f"   Account mode: {'TEST' if secret_key.startswith('sk_test') else 'LIVE'}")
        print(f"   Available balance: {balance.available[0].amount / 100:.2f} {balance.available[0].currency.upper()}")
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

if __name__ == "__main__":
    print("=" * 60)
    print("Stripe Configuration Test")
    print("=" * 60 + "\n")
    
    success = test_stripe_config()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ All tests passed! Your Stripe integration is ready.")
        print("\nYou can now:")
        print("  1. Start the server: python web_server.py")
        print("  2. Book a flight in the web UI")
        print("  3. Payment will be processed via Stripe")
        print("\nTest card: 4242 4242 4242 4242")
        print("=" * 60)
        sys.exit(0)
    else:
        print("❌ Configuration issues found. Please fix them and try again.")
        print("=" * 60)
        sys.exit(1)
