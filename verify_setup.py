#!/usr/bin/env python3
"""
Simple script to verify the database setup and configuration.
Run this before starting the bot to ensure everything is configured correctly.
"""
import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine


async def verify_database_connection():
    """Verify database connection using the configured DATABASE_URL"""
    try:
        # Load settings
        from app.config import settings

        print("=" * 60)
        print("Verifying bot configuration...")
        print("=" * 60)
        print()

        # Check critical settings
        print("✓ Bot token:", "SET" if settings.BOT_TOKEN else "MISSING")
        print("✓ Admin IDs:", settings.ADMIN_IDS if settings.ADMIN_IDS else "MISSING")
        print("✓ Database URL:", settings.database_url)
        print()

        # Test database connection
        print("Testing database connection...")
        engine = create_async_engine(settings.database_url, echo=False)

        async with engine.connect() as conn:
            result = await conn.execute(sqlalchemy.text("SELECT 1"))
            await result.fetchone()

        await engine.dispose()

        print("✓ Database connection successful!")
        print()
        print("=" * 60)
        print("All checks passed! You can now run the bot with:")
        print("  python bot.py")
        print("  or")
        print("  python -m app.bot")
        print("=" * 60)
        return True

    except ImportError as e:
        print(f"✗ Import error: {e}")
        print("Make sure all dependencies are installed:")
        print("  pip install -r requirements.txt")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        print()
        print("Common issues:")
        print("1. Make sure PostgreSQL is running")
        print("2. Check your .env file has correct DATABASE_URL")
        print("3. Verify database exists: CREATE DATABASE raffle_bot;")
        print()
        print("Example DATABASE_URL:")
        print("  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/raffle_bot")
        return False


if __name__ == "__main__":
    import sqlalchemy
    success = asyncio.run(verify_database_connection())
    sys.exit(0 if success else 1)
