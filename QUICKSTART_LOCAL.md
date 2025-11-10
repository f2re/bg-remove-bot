# Quick Start Guide: Running Bot with Local PostgreSQL

This guide will help you quickly set up and run the bot with a local PostgreSQL database without Docker.

## Prerequisites

- Python 3.11 or higher
- PostgreSQL 15 or higher installed and running
- Git (to clone the repository)

## Step-by-Step Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up PostgreSQL Database

#### If PostgreSQL is installed locally:

```bash
# Login to PostgreSQL
psql -U postgres

# Create the database
CREATE DATABASE raffle_bot;

# Exit
\q
```

#### If you want to run PostgreSQL in Docker only:

```bash
docker run -d \
  --name postgres \
  -e POSTGRES_DB=raffle_bot \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres:15
```

### 3. Configure Environment Variables

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` and set the required values:

```env
# Required: Your Telegram bot token from @BotFather
BOT_TOKEN=your_bot_token_here

# Required: Comma-separated list of admin Telegram IDs
ADMIN_IDS=123456789,987654321

# Required: Database connection string
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/raffle_bot

# Required: API keys (get from respective services)
OPENROUTER_API_KEY=your_api_key_here
ROBOKASSA_LOGIN=your_login
ROBOKASSA_PASSWORD1=your_password1
ROBOKASSA_PASSWORD2=your_password2
```

### 4. Run Database Migrations

```bash
alembic upgrade head
```

This will create all necessary tables in your database.

### 5. Verify Setup (Optional but Recommended)

```bash
python verify_setup.py
```

This script will verify:
- Configuration is loaded correctly
- Database connection works
- All required environment variables are set

### 6. Start the Bot

You can start the bot using any of these commands:

```bash
# Option 1: Run directly
python bot.py

# Option 2: Run as a module
python -m app.bot

# Option 3: Using python3 explicitly
python3 bot.py
```

## Troubleshooting

### Error: "ModuleNotFoundError"
**Solution:** Install dependencies with `pip install -r requirements.txt`

### Error: "Connection refused" or database connection errors
**Solution:**
1. Make sure PostgreSQL is running: `sudo systemctl status postgresql` (Linux) or check Docker container
2. Verify the DATABASE_URL in your `.env` file
3. Test connection: `psql postgresql://postgres:postgres@localhost:5432/raffle_bot`

### Error: "No module named 'app'"
**Solution:** Run the bot from the project root directory

### Error: Missing BOT_TOKEN or other environment variables
**Solution:**
1. Make sure `.env` file exists in the project root
2. Verify all required variables are set
3. Don't use quotes around values in `.env` file

### Database doesn't have tables
**Solution:** Run migrations with `alembic upgrade head`

## DATABASE_URL Format Explained

The DATABASE_URL follows this pattern:
```
postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DATABASE
```

Breaking it down:
- `postgresql+asyncpg://` - Protocol (asyncpg driver for async operations)
- `USER` - PostgreSQL username (default: postgres)
- `PASSWORD` - PostgreSQL password
- `HOST` - Database host (localhost for local setup)
- `PORT` - Database port (default: 5432)
- `DATABASE` - Database name (raffle_bot in our case)

Example:
```
DATABASE_URL=postgresql+asyncpg://postgres:mypassword@localhost:5432/raffle_bot
```

## Alternative Configuration

Instead of using `DATABASE_URL`, you can also configure the database using individual variables in `.env`:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=raffle_bot
DB_USER=postgres
DB_PASSWORD=postgres
```

**Note:** If `DATABASE_URL` is set, it takes precedence over individual DB_* variables.

## Stopping the Bot

Press `Ctrl+C` in the terminal where the bot is running.

## Next Steps

- Read the full [README.md](README.md) for detailed information
- Check bot logs for any errors
- Test bot functionality by sending `/start` to your bot on Telegram
- Configure Robokassa webhooks for payment processing
- Add your Telegram ID to ADMIN_IDS to access admin panel

## Getting Help

If you encounter issues:
1. Check the logs for error messages
2. Verify all environment variables are set correctly
3. Make sure PostgreSQL is running and accessible
4. Run `python verify_setup.py` to diagnose configuration issues
