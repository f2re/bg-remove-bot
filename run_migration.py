#!/usr/bin/env python3
"""
Direct migration script to add admin_id column to support_tickets table.
This script bypasses the full config requirements and runs the migration directly.
"""
import asyncio
import os
import sys
from sqlalchemy.ext.asyncio import create_async_engine


async def run_migration():
    """Add admin_id column to support_tickets if it doesn't exist."""

    # Try to get DATABASE_URL from environment
    database_url = os.getenv('DATABASE_URL')

    # If not found, construct from individual vars
    if not database_url:
        db_host = os.getenv('DB_HOST', 'localhost')
        db_port = os.getenv('DB_PORT', '5432')
        db_name = os.getenv('DB_NAME', 'bg_removal_bot')
        db_user = os.getenv('DB_USER', 'postgres')
        db_password = os.getenv('DB_PASSWORD', 'postgres')
        database_url = f"postgresql+asyncpg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    print(f"Connecting to database...")

    try:
        engine = create_async_engine(database_url, echo=True)

        async with engine.begin() as conn:
            # Check if admin_id column already exists
            result = await conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='support_tickets' AND column_name='admin_id'
                """
            )
            exists = result.fetchone() is not None

            if exists:
                print("✓ Column 'admin_id' already exists in support_tickets table")
            else:
                print("Adding 'admin_id' column to support_tickets table...")
                await conn.execute(
                    """
                    ALTER TABLE support_tickets
                    ADD COLUMN admin_id BIGINT
                    """
                )
                print("✓ Column 'admin_id' added successfully!")

            # Also check and create support_messages table if needed
            result = await conn.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_name='support_messages'
                """
            )
            exists = result.fetchone() is not None

            if exists:
                print("✓ Table 'support_messages' already exists")
            else:
                print("Creating 'support_messages' table...")
                await conn.execute(
                    """
                    CREATE TABLE support_messages (
                        id SERIAL PRIMARY KEY,
                        ticket_id INTEGER NOT NULL REFERENCES support_tickets(id),
                        sender_telegram_id BIGINT NOT NULL,
                        is_admin BOOLEAN NOT NULL DEFAULT false,
                        message TEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                print("✓ Table 'support_messages' created successfully!")

        await engine.dispose()
        print("\n✓ Migration completed successfully!")
        return 0

    except Exception as e:
        print(f"\n✗ Migration failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run_migration()))
