## Архитектура проекта

### Структура каталогов

```
/
├── app/
│   ├── __init__.py
│   ├── bot.py                 # Инициализация бота
│   ├── config.py              # Конфигурация (env переменные)
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── user.py            # Обработчики пользователя
│   │   ├── admin.py           # Админ-панель
│   │   ├── payment.py         # Обработка платежей
│   │   └── support.py         # Обратная связь
│   ├── services/
│   │   ├── __init__.py
│   │   ├── openrouter.py      # API OpenRouter
│   │   ├── image_processor.py # Обработка изображений
│   │   ├── robokassa.py       # Платежи Robokassa
│   │   └── prompt_builder.py  # Генерация промптов
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py          # SQLAlchemy модели
│   │   └── crud.py            # CRUD операции
│   ├── keyboards/
│   │   ├── __init__.py
│   │   ├── user_kb.py         # Клавиатуры пользователя
│   │   └── admin_kb.py        # Клавиатуры админа
│   └── utils/
│       ├── __init__.py
│       ├── validators.py      # Валидация данных
│       └── decorators.py      # Декораторы (admin_only и т.д.)
├── alembic/                   # Миграции БД
├── static/
│   └── legal/                 # PDF документы (оферта, возврат)
├── .env
├── requirements.txt
├── README.md
└── docker-compose.yml
```

## Схема базы данных PostgreSQL

```sql
-- Таблица пользователей
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    free_images_left INTEGER DEFAULT 3,
    total_images_processed INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица пакетов изображений
CREATE TABLE packages (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    images_count INTEGER NOT NULL,
    price_rub DECIMAL(10, 2) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);

-- Таблица заказов
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    package_id INTEGER REFERENCES packages(id),
    robokassa_invoice_id VARCHAR(255) UNIQUE,
    amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending', -- pending, paid, refunded
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMP
);

-- Таблица обработанных изображений
CREATE TABLE processed_images (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    order_id INTEGER REFERENCES orders(id),
    original_file_id VARCHAR(255),
    processed_file_id VARCHAR(255),
    prompt_used TEXT,
    is_free BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица обращений в поддержку
CREATE TABLE support_tickets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    order_id INTEGER REFERENCES orders(id),
    message TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'open', -- open, in_progress, resolved
    admin_response TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);

-- Таблица администраторов
CREATE TABLE admins (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    role VARCHAR(50) DEFAULT 'admin', -- admin, super_admin
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Структура меню и UI/UX

### Главное меню (кнопки)
```
📸 Обработать изображение
💎 Купить пакет
📊 Мой баланс
ℹ️ Информация
💬 Поддержка
```

### Подменю "Купить пакет"
```
🎁 Бесплатно: 3 изображения (осталось: X)
━━━━━━━━━━━━━━━━━━
💰 1 изображение - 50₽
💰 5 изображений - 200₽ (скидка 20%)
💰 10 изображений - 350₽ (скидка 30%)
💰 50 изображений - 1500₽ (скидка 40%)
```

### Подменю "Информация"
```
📄 Оферта
💸 Условия возврата
🔒 Политика конфиденциальности
❓ Как это работает
```

### Админ-меню (для администраторов)
```
👥 Статистика пользователей
📦 Заказы (последние 50)
💬 Обращения в поддержку
➕ Добавить генерации
💵 Оформить возврат
📈 Аналитика (графики)
```

## Логика работы бота

### Процесс обработки изображения

1. **Пользователь отправляет изображение**
2. **Проверка баланса** (бесплатные или платные изображения)
3. **Анализ изображения** для построения промпта
4. **Генерация промпта** с учетом:
   - Наличия сложных краев (волосы, мех, стекло)
   - Прозрачных объектов
   - Теней и освещения
   - Размытия движения
5. **Вызов OpenRouter API** (модель nano banana)
6. **Обработка результата** и отправка пользователю
7. **Обновление баланса** в БД

### Пример оптимального промпта

```python
def build_prompt(image_analysis):
    base_prompt = "Remove background completely, "
    
    if image_analysis.get('has_hair'):
        base_prompt += "preserve detailed hair strands with soft edges, avoid halos, "
    
    if image_analysis.get('has_transparent_objects'):
        base_prompt += "keep glass reflections and realistic transparency, "
    
    if image_analysis.get('has_motion_blur'):
        base_prompt += "preserve motion blur and smooth edges, "
    
    base_prompt += "maintain natural lighting, clean cutout, high precision"
    
    return base_prompt
```

## Интеграция с Robokassa

### Процесс оплаты

1. Пользователь выбирает пакет
2. Генерируется уникальный invoice_id
3. Формируется платежная ссылка Robokassa
4. Пользователь переходит на страницу оплаты
5. После оплаты webhook от Robokassa обновляет статус заказа
6. Начисляются изображения на баланс пользователя
7. Отправляется чек по ФЗ-54

### Пример кода интеграции

```python
# services/robokassa.py
import hashlib
from config import ROBOKASSA_LOGIN, ROBOKASSA_PASSWORD1, ROBOKASSA_PASSWORD2

class RobokassaService:
    @staticmethod
    def generate_payment_link(order_id, amount, description):
        signature = hashlib.md5(
            f"{ROBOKASSA_LOGIN}:{amount}:{order_id}:{ROBOKASSA_PASSWORD1}".encode()
        ).hexdigest()
        
        return (
            f"https://auth.robokassa.ru/Merchant/Index.aspx?"
            f"MerchantLogin={ROBOKASSA_LOGIN}&"
            f"OutSum={amount}&"
            f"InvId={order_id}&"
            f"Description={description}&"
            f"SignatureValue={signature}&"
            f"IsTest=0"
        )
    
    @staticmethod
    def verify_signature(out_sum, inv_id, signature):
        expected = hashlib.md5(
            f"{out_sum}:{inv_id}:{ROBOKASSA_PASSWORD2}".encode()
        ).hexdigest()
        return signature.lower() == expected.lower()
```

## Ключевые функции

### Пользовательские функции
- ✅ Удаление фона с изображений
- ✅ 3 бесплатные обработки при регистрации
- ✅ Покупка пакетов изображений
- ✅ Просмотр баланса и истории
- ✅ Обратная связь с администратором
- ✅ Доступ к правовой информации

### Административные функции
- ✅ Просмотр статистики (всего пользователей, обработано изображений, выручка)
- ✅ Управление заказами
- ✅ Обработка обращений в поддержку
- ✅ Ручное добавление генераций пользователю
- ✅ Оформление возвратов
- ✅ Экспорт данных для аналитики

## Ценообразование

На основе стоимости API OpenRouter для nano banana (примерно $0.001-0.005 за запрос):

| Пакет | Цена | Цена за изображение | Маржа |
|-------|------|---------------------|-------|
| 1 шт | 50₽ | 50₽ | ~95% |
| 5 шт | 200₽ | 40₽ | ~96% |
| 10 шт | 350₽ | 35₽ | ~97% |
| 50 шт | 1500₽ | 30₽ | ~97% |

## Правовые документы (требования Robokassa)

### 1. Публичная оферта
Описание услуг, порядок заключения договора, права и обязанности сторон

### 2. Политика возврата
- Возврат в течение 7 дней с момента покупки
- При условии использования менее 20% купленных изображений
- Возврат пропорционально неиспользованным изображениям

### 3. Политика конфиденциальности
Обработка персональных данных согласно 152-ФЗ

### 4. Описание услуг
Детальное описание процесса обработки изображений

## Рекомендации по UI/UX

### Лучшие практики Telegram-ботов

1. **Минималистичный дизайн** - используйте эмодзи для визуального разделения
2. **Inline-кнопки** для навигации вместо текстовых команд
3. **Прогресс-индикаторы** при обработке изображений ("⏳ Обрабатываю...")
4. **Быстрый доступ** к основным функциям через постоянное меню
5. **Понятные сообщения об ошибках** с указанием решения
6. **Подтверждение действий** перед оплатой

### Пример диалога

```
Пользователь: /start
Бот: 👋 Привет! Я помогу удалить фон с изображений.

🎁 Вам доступно 3 бесплатные обработки!

Просто отправьте мне фото, и я уберу фон за несколько секунд.

[Кнопки главного меню]

---

Пользователь: [отправляет фото]
Бот: ⏳ Обрабатываю изображение...

✅ Готово! Фон успешно удален.

📊 Осталось бесплатных обработок: 2

Хотите купить пакет для постоянного использования?
[💎 Посмотреть тарифы]
```

## Механизм обратной связи

### Процесс создания обращения

1. Пользователь нажимает "💬 Поддержка"
2. Выбирает тип обращения:
   - ❓ Вопрос по работе
   - 🐛 Сообщить о проблеме
   - 💸 Вопрос по оплате
   - 📦 Запрос возврата
3. Описывает проблему текстом
4. Обращение сохраняется в БД и пересылается всем администраторам
5. Администратор отвечает через админ-панель
6. Ответ приходит пользователю в бот

## Технологический стек

```python
# requirements.txt
aiogram==3.4.1                # Telegram Bot Framework
sqlalchemy==2.0.25            # ORM
asyncpg==0.29.0               # PostgreSQL драйвер
alembic==1.13.1               # Миграции БД
aiohttp==3.9.1                # HTTP клиент
python-dotenv==1.0.0          # Env переменные
pillow==10.2.0                # Обработка изображений
pydantic==2.5.3               # Валидация данных
redis==5.0.1                  # Кэширование (опционально)
```

## Конфигурация (.env)

```env
# Telegram
BOT_TOKEN=your_bot_token
ADMIN_IDS=123456789,987654321

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=bg_removal_bot
DB_USER=postgres
DB_PASSWORD=your_password

# OpenRouter
OPENROUTER_API_KEY=your_api_key
OPENROUTER_MODEL=nano-banana-ai/model-name

# Robokassa
ROBOKASSA_LOGIN=your_login
ROBOKASSA_PASSWORD1=your_password1
ROBOKASSA_PASSWORD2=your_password2
ROBOKASSA_TEST_MODE=False

# Pricing (в копейках)
PACKAGE_1_PRICE=5000
PACKAGE_5_PRICE=20000
PACKAGE_10_PRICE=35000
PACKAGE_50_PRICE=150000
```

## Пример кода основных модулей

### Обработчик изображений

```python
# handlers/user.py
from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from services.image_processor import ImageProcessor
from services.openrouter import OpenRouterService
from database.crud import get_user_balance, decrease_balance

router = Router()

@router.message(F.photo)
async def process_image(message: Message):
    user_id = message.from_user.id
    balance = await get_user_balance(user_id)
    
    if balance <= 0:
        await message.answer(
            "❌ У вас закончились изображения!\n\n"
            "💎 Купите пакет для продолжения работы.",
            reply_markup=get_packages_keyboard()
        )
        return
    
    status_msg = await message.answer("⏳ Обрабатываю изображение...")
    
    # Скачивание фото
    photo = message.photo[-1]
    file = await message.bot.download(photo)
    
    # Анализ и построение промпта
    processor = ImageProcessor()
    analysis = processor.analyze_image(file)
    prompt = processor.build_prompt(analysis)
    
    # Вызов OpenRouter API
    openrouter = OpenRouterService()
    result = await openrouter.remove_background(file, prompt)
    
    if result.success:
        # Отправка результата
        output_file = FSInputFile(result.image_path)
        await message.answer_photo(
            output_file,
            caption=f"✅ Готово!\n\n📊 Осталось изображений: {balance - 1}"
        )
        
        # Обновление баланса
        await decrease_balance(user_id)
        
        await status_msg.delete()
    else:
        await status_msg.edit_text("❌ Ошибка обработки. Попробуйте другое фото.")
```

### Админ-панель

```python
# handlers/admin.py
from aiogram import Router
from aiogram.filters import Command
from utils.decorators import admin_only
from database.crud import get_statistics

router = Router()

@router.message(Command("admin"))
@admin_only
async def admin_panel(message: Message):
    stats = await get_statistics()
    
    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"📸 Обработано изображений: {stats['total_processed']}\n"
        f"💰 Выручка: {stats['revenue']}₽\n"
        f"📦 Активных заказов: {stats['active_orders']}\n"
        f"💬 Открытых обращений: {stats['open_tickets']}"
    )
    
    await message.answer(text, reply_markup=get_admin_keyboard())
```

## Развертывание

### Docker Compose

```yaml
version: '3.8'

services:
  bot:
    build: .
    env_file: .env
    depends_on:
      - db
      - redis
    restart: unless-stopped
  
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
    restart: unless-stopped

volumes:
  postgres_data:
```

## Контрольный список запуска

- [ ] Создать бота через @BotFather
- [ ] Настроить PostgreSQL и выполнить миграции
- [ ] Зарегистрироваться в OpenRouter и получить API ключ
- [ ] Подключить магазин в Robokassa
- [ ] Добавить webhook для обработки платежей
- [ ] Заполнить таблицу packages начальными данными
- [ ] Добавить telegram_id администраторов в таблицу admins
- [ ] Подготовить PDF документы (оферта, возврат, конфиденциальность)
- [ ] Протестировать полный цикл: регистрация → бесплатная обработка → покупка → обработка
- [ ] Протестировать возврат средств
- [ ] Настроить мониторинг и логирование

Этот план следует принципам DRY и KISS, обеспечивает простой и понятный интерфейс, соответствует требованиям Robokassa и предоставляет все необходимые функции для успешной работы бота.

