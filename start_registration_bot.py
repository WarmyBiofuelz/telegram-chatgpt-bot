#!/usr/bin/env python3
"""
Startup script for Unified Horoscope Bot
Run this to start the unified bot with registration and horoscope functionality.
"""

import asyncio
from registration_bot import main

if __name__ == "__main__":
    print("🌟 Starting Unified Horoscope Bot...")
    print("This bot handles user registration, database management, and horoscope generation.")
    print("Press Ctrl+C to stop.")
    asyncio.run(main())
