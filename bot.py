#!/usr/bin/env python3
"""
Entry point for running the bot.
This file allows running the bot with: python bot.py or python3 bot.py
"""
from app.bot import main
import asyncio
import logging

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot stopped with error: {e}")
