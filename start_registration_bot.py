#!/usr/bin/env python3
"""
Startup script for Registration Bot
Run this to start the registration bot only.
"""

import asyncio
from registration_bot import main

if __name__ == "__main__":
    print("🌟 Starting Registration Bot...")
    print("This bot handles user registration and database management.")
    print("Press Ctrl+C to stop.")
    asyncio.run(main())
