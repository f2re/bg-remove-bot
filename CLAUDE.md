# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Telegram bot for AI-powered background removal from images with integrated payment processing. The bot uses OpenRouter API (specifically Google Gemini 2.5 Flash Image) for image editing and YooKassa (ЮКасса) for handling payments in rubles. Users get 3 free image processing operations, then purchase packages.

## Development Commands

### Running the Bot

```bash
# Local development (requires PostgreSQL running)
python -m app.bot

# Docker (recommended)
docker-compose up -d

# View logs
docker-compose logs -f bot
```

### Database Operations

```bash
# Apply migrations
alembic upgrade head

# Create new migration (after modifying models)
alembic revision --autogenerate -m "Description"

# Rollback one migration
alembic downgrade -1

# Access PostgreSQL
docker-compose exec db psql -U postgres -d bg_removal_bot
```

### Dependencies

```bash
# Install dependencies
pip install -r requirements.txt
```

## Architecture

### Core Request Flow

**Image Processing Flow:**
1. User sends photo → `app/handlers/user.py:process_image_handler()`
2. Balance checked via `app/database/crud.py:get_user_balance()`
3. Image analyzed → `app/services/image_processor.py:ImageProcessor.analyze_image()`
4. Prompt built → `app/services/prompt_builder.py:PromptBuilder.build_prompt()`
5. API call → `app/services/openrouter.py:OpenRouterService.remove_background()`
6. Balance decremented and image saved to DB

**Payment Flow:**
1. User selects package → `app/handlers/payment.py:buy_package_handler()`
2. Order created in DB with unique order_id
3. YooKassa payment created → `app/services/yookassa.py:YookassaService.create_payment()`
4. User redirected to YooKassa payment page
5. Webhook received → `app/handlers/payment.py:process_payment_webhook()`
6. Order marked paid, notifications sent via `notify_payment_success()`

### Database Architecture

The bot uses SQLAlchemy 2.0+ with async support. Key relationships:
- **Users** have many **Orders** and **ProcessedImages**
- **Orders** link **Users** to **Packages** and track payment status via `invoice_id` (YooKassa payment_id)
- **Balance calculation** is dynamic: free images stored directly on User, paid images calculated from Order.status='paid' minus used ProcessedImages where is_free=False

Critical: The database session management uses a global `db` instance from `app/database/__init__.py`. Always use:
```python
from app.database import get_db
db = get_db()
async with db.get_session() as session:
    # Your DB operations
```

### Handler Router Registration

All handlers use aiogram's Router pattern. New handlers must be registered in `app/bot.py`:
```python
dp.include_router(your_handler.router)
```

The registration order matters for FSM state handling - more specific routers should come before generic ones.

### Admin Access Control

The `@admin_only` decorator checks BOTH:
1. `settings.admin_ids_list` from ADMIN_IDS env var (comma-separated)
2. Database `admins` table

This dual-check allows bootstrap (env var) and dynamic admin management (DB table).

### OpenRouter Integration Specifics

**Model:** `google/gemini-2.5-flash-image-preview` (configurable via OPENROUTER_MODEL)

**Critical implementation details:**
- Request must include `"modalities": ["text", "image"]` to enable image output
- Response format: check `choices[0].message.images[]` for base64 data URLs
- Image data can be: `data:image/png;base64,xxx` or direct URL requiring download
- Prompts must be very specific about "remove background completely, make transparent"
- The `PromptBuilder` generates detailed prompts based on image analysis (hair, glass, blur detection)

### YooKassa Payment Integration

**Authentication:** Basic Auth using `YOOKASSA_SHOP_ID` and `YOOKASSA_SECRET_KEY`

**Payment creation flow:**
- Create payment via `Payment.create()` from yookassa SDK
- Metadata includes `order_id` for tracking
- Payment returns `payment_id` which is stored as `invoice_id` in Orders table
- User redirected to `confirmation_url` for payment

**Webhook verification:**
- YooKassa SDK automatically validates webhook signatures
- Payment status checked: must be `succeeded` and `paid=True`
- Metadata contains original `order_id` for reference

**Fiscal compliance (54-ФЗ):**
- Receipt automatically generated if email or phone provided
- VAT code: 1 (НДС 20%)
- Payment subject: "service"

## Configuration Management

All config via `app/config.py` using pydantic-settings. Settings loaded from `.env` file:
- Never commit `.env` (use `.env.example` as template)
- `settings.admin_ids_list` property converts comma-separated string to list of ints
- `settings.database_url` property builds async PostgreSQL connection string

## State Management

The bot uses aiogram's FSM (Finite State Machine) for multi-step interactions:
- `PaymentStates.waiting_for_payment` - during checkout
- `SupportStates.waiting_for_message` - collecting support message
- `AdminStates.*` - various admin workflows

State data stored via `state.update_data()` and retrieved with `state.get_data()`.

## Image Processing Pipeline

**ImageProcessor Analysis:**
- Detects complex edges (hair/fur) via gradient variance
- Detects transparency by checking alpha channel or brightness > 240
- Detects blur via Laplacian variance
- Returns dict used by PromptBuilder to construct optimal prompt

**Prompt Construction Philosophy:**
The prompts are intentionally verbose and specific because Gemini image editing requires explicit instructions. Generic prompts like "remove background" produce poor results. The current prompts specify:
- Exact transparency requirements (alpha = 0)
- Edge handling for different materials
- Output format (PNG with transparency)

## Key Constraints

1. **Balance calculation is NOT stored** - it's computed on-the-fly from orders and processed_images tables
2. **Free images take priority** - always use free_images_left before paid images
3. **File IDs are Telegram file IDs** - stored as strings, used to track original/processed files
4. **Invoice IDs are YooKassa payment_ids** - webhook uses this to match payments to orders
5. **Admin notifications** - payment success triggers notifications to all admins in ADMIN_IDS

## Missing Components (TODOs)

1. **Notification Service** - `app/handlers/payment.py` imports `NotificationService` which doesn't exist yet
2. **Webhook endpoint** - Need web server to receive YooKassa callbacks (consider aiohttp web server)
3. **Legal documents** - `static/legal/` directory exists but PDFs not created

## Troubleshooting Guide

**"No module named app"** - Run as module: `python -m app.bot` not `python app/bot.py`

**Database connection errors** - Check DATABASE_URL format: `postgresql+asyncpg://user:pass@host:port/dbname`

**OpenRouter errors** - Model name must be exact. Check available models at openrouter.ai/docs

**Payment webhook not working** - YooKassa needs public HTTPS endpoint, use ngrok for local testing. Configure webhook URL in YooKassa dashboard.

**Admin commands not working** - Verify your telegram_id is in ADMIN_IDS env var OR admins table
