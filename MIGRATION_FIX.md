# Database Migration Fix

## Problem

The `support_tickets` table is missing the `admin_id` column, causing this error:

```
ProgrammingError: column "admin_id" of relation "support_tickets" does not exist
```

## Solution

You need to apply migration `002_add_support_messages` which adds the `admin_id` column and creates the `support_messages` table.

## How to Fix

### Option 1: Using Alembic (Recommended)

1. Make sure you have your `.env` file with at least the database connection info:
   ```bash
   DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/bg_removal_bot
   # OR individual variables:
   # DB_HOST=localhost
   # DB_PORT=5432
   # DB_NAME=bg_removal_bot
   # DB_USER=postgres
   # DB_PASSWORD=postgres
   ```

2. Run the migration:
   ```bash
   # If using alembic directly:
   alembic upgrade head

   # Or using Python:
   python -c "from alembic.config import Config; from alembic import command; cfg = Config('alembic.ini'); command.upgrade(cfg, 'head')"
   ```

### Option 2: Using the Direct Migration Script

If you don't want to deal with environment configuration, use the included script:

```bash
# Set the database connection as environment variables:
export DATABASE_URL="postgresql+asyncpg://user:password@localhost:5432/bg_removal_bot"

# Or individual variables:
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=bg_removal_bot
export DB_USER=postgres
export DB_PASSWORD=postgres

# Run the migration script:
python run_migration.py
```

### Option 3: Manual SQL (If all else fails)

Connect to your PostgreSQL database and run:

```sql
-- Add admin_id column to support_tickets
ALTER TABLE support_tickets ADD COLUMN admin_id BIGINT;

-- Create support_messages table
CREATE TABLE support_messages (
    id SERIAL PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES support_tickets(id),
    sender_telegram_id BIGINT NOT NULL,
    is_admin BOOLEAN NOT NULL DEFAULT false,
    message TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

## Verification

After running the migration, verify it worked:

```bash
# Connect to PostgreSQL
psql -U postgres -d bg_removal_bot

# Check if the column exists:
\d support_tickets

# You should see 'admin_id' in the list of columns
```

## Next Steps

After fixing the database schema, restart your bot:

```bash
python -m app.bot
```

The error should be resolved!
