#!/usr/bin/env python3
"""
Temporary main.py for hosting service compatibility
This file runs the registration bot to maintain compatibility
with hosting services that expect a main.py file.
"""

import asyncio
from registration_bot import main

if __name__ == "__main__":
    print("🌟 Starting Registration Bot (via main.py)...")
    print("This is a temporary compatibility file.")
    print("For production, use: python start_registration_bot.py")
    asyncio.run(main())
