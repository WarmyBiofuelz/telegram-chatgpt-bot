#!/usr/bin/env python3
"""
Startup script for Horoscope Bot
Run this to start the horoscope bot only.
"""

import asyncio
from horoscope_bot import main

if __name__ == "__main__":
    print("🔮 Starting Horoscope Bot...")
    print("This bot generates and sends horoscopes from database data.")
    print("Press Ctrl+C to stop.")
    asyncio.run(main())
