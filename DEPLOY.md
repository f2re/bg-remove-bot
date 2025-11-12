# Production Deployment Guide

Полное руководство по развертыванию Background Removal Telegram Bot в production окружении.

## Содержание

1. [Требования](#требования)
2. [Подготовка сервера](#подготовка-сервера)
3. [Установка PostgreSQL](#установка-postgresql)
4. [Установка приложения](#установка-приложения)
5. [Настройка systemd](#настройка-systemd)
6. [Мониторинг и логи](#мониторинг-и-логи)
7. [Обновление приложения](#обновление-приложения)
8. [Резервное копирование](#резервное-копирование)
9. [Troubleshooting](#troubleshooting)

## Требования

### Минимальные требования к серверу

- **OS**: Ubuntu 20.04/22.04 LTS или Debian 11/12
- **CPU**: 1 vCore (рекомендуется 2+)
- **RAM**: 1GB (рекомендуется 2GB+)
- **Disk**: 10GB SSD
- **Network**: Стабильное интернет-соединение

### Необходимое ПО

- Python 3.11+
- PostgreSQL 13+
- Git
- systemd

## Подготовка сервера

### 1. Обновление системы

```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Установка необходимых пакетов

```bash
sudo apt install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    postgresql \
    postgresql-contrib \
    git \
    nginx \
    certbot \
    python3-certbot-nginx \
    build-essential \
    libpq-dev
```

### 3. Настройка firewall (UFW)

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

## Установка PostgreSQL

### 1. Настройка PostgreSQL

```bash
# Переключитесь на пользователя postgres
sudo -u postgres psql

# Выполните в psql:
-- Создайте пользователя с безопасным паролем
CREATE USER bgremove_user WITH PASSWORD 'CHANGE_THIS_TO_SECURE_PASSWORD';

-- Создайте базу данных
CREATE DATABASE bg_removal_bot OWNER bgremove_user;

-- Дайте права
GRANT ALL PRIVILEGES ON DATABASE bg_removal_bot TO bgremove_user;

-- Выйдите
\q
```

### 2. Настройка аутентификации PostgreSQL

Отредактируйте `/etc/postgresql/*/main/pg_hba.conf`:

```bash
sudo nano /etc/postgresql/14/main/pg_hba.conf
```

Убедитесь, что есть строка:
```
local   all             bgremove_user                           md5
```

Перезапустите PostgreSQL:
```bash
sudo systemctl restart postgresql
```

### 3. Проверка подключения

```bash
psql -U bgremove_user -d bg_removal_bot -h localhost
# Введите пароль и проверьте подключение
\q
```

## Установка приложения

### 1. Создание директории

```bash
sudo mkdir -p /opt/bg-remove-bot
sudo chown www-data:www-data /opt/bg-remove-bot
cd /opt/bg-remove-bot
```

### 2. Клонирование репозитория

```bash
sudo -u www-data git clone https://github.com/yourusername/bg-remove-bot.git .
```

### 3. Создание виртуального окружения

```bash
sudo -u www-data python3.11 -m venv venv
sudo -u www-data /opt/bg-remove-bot/venv/bin/pip install --upgrade pip
sudo -u www-data /opt/bg-remove-bot/venv/bin/pip install -r requirements.txt
```

### 4. Настройка переменных окружения

```bash
sudo -u www-data cp .env.example .env
sudo -u www-data nano .env
```

Заполните **все обязательные переменные**:

```env
# Telegram
BOT_TOKEN=1234567890:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
ADMIN_IDS=123456789

# Database
DATABASE_URL=postgresql+asyncpg://bgremove_user:SECURE_PASSWORD@localhost:5432/bg_removal_bot

# OpenRouter
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENROUTER_MODEL=google/gemini-2.5-flash-image-preview

# Robokassa
ROBOKASSA_LOGIN=your_shop_login
ROBOKASSA_PASSWORD1=password1_from_robokassa
ROBOKASSA_PASSWORD2=password2_from_robokassa
ROBOKASSA_TEST_MODE=False

# Pricing (в копейках)
PACKAGE_1_PRICE=5000
PACKAGE_5_PRICE=20000
PACKAGE_10_PRICE=35000
PACKAGE_50_PRICE=150000

# Free images
FREE_IMAGES_COUNT=3

# Logging
LOG_LEVEL=INFO
```

### 5. Применение миграций

```bash
sudo -u www-data /opt/bg-remove-bot/venv/bin/alembic upgrade head
```

### 6. Проверка работоспособности

```bash
# Тестовый запуск бота
sudo -u www-data /opt/bg-remove-bot/venv/bin/python -m app.bot
# Ctrl+C для остановки после проверки
```

## Настройка systemd

### 1. Копирование service файла

```bash
sudo cp /opt/bg-remove-bot/bg-remove-bot.service /etc/systemd/system/
```

### 2. Проверка конфигурации

Убедитесь, что пути в `/etc/systemd/system/bg-remove-bot.service` корректны:

```ini
[Unit]
Description=Background Removal Telegram Bot
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/bg-remove-bot
Environment="PATH=/opt/bg-remove-bot/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/opt/bg-remove-bot/venv/bin/python -m app.bot
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=bg-remove-bot

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/bg-remove-bot

[Install]
WantedBy=multi-user.target
```

### 3. Запуск сервиса

```bash
# Перезагрузите конфигурацию systemd
sudo systemctl daemon-reload

# Включите автозапуск
sudo systemctl enable bg-remove-bot

# Запустите сервис
sudo systemctl start bg-remove-bot

# Проверьте статус
sudo systemctl status bg-remove-bot
```

## Мониторинг и логи

### Просмотр логов

```bash
# Логи в реальном времени
sudo journalctl -u bg-remove-bot -f

# Последние 100 строк
sudo journalctl -u bg-remove-bot -n 100

# Логи за сегодня
sudo journalctl -u bg-remove-bot --since today

# Логи с конкретного времени
sudo journalctl -u bg-remove-bot --since "2024-01-01 10:00:00"
```

### Управление сервисом

```bash
# Статус
sudo systemctl status bg-remove-bot

# Запуск
sudo systemctl start bg-remove-bot

# Остановка
sudo systemctl stop bg-remove-bot

# Перезапуск
sudo systemctl restart bg-remove-bot

# Перезагрузка конфигурации
sudo systemctl reload bg-remove-bot
```

### Мониторинг ресурсов

```bash
# CPU и Memory usage
sudo systemctl status bg-remove-bot | grep -E 'CPU|Memory'

# Детальная информация
sudo systemd-cgtop

# PostgreSQL мониторинг
sudo -u postgres psql -c "SELECT * FROM pg_stat_activity WHERE datname='bg_removal_bot';"
```

## Обновление приложения

### Стандартное обновление

```bash
# 1. Остановите сервис
sudo systemctl stop bg-remove-bot

# 2. Создайте backup (см. раздел "Резервное копирование")
sudo -u postgres pg_dump bg_removal_bot > /tmp/backup_$(date +%Y%m%d_%H%M%S).sql

# 3. Обновите код
cd /opt/bg-remove-bot
sudo -u www-data git pull

# 4. Обновите зависимости (если requirements.txt изменился)
sudo -u www-data /opt/bg-remove-bot/venv/bin/pip install -r requirements.txt --upgrade

# 5. Примените миграции
sudo -u www-data /opt/bg-remove-bot/venv/bin/alembic upgrade head

# 6. Запустите сервис
sudo systemctl start bg-remove-bot

# 7. Проверьте статус
sudo systemctl status bg-remove-bot
sudo journalctl -u bg-remove-bot -f
```

### Откат при проблемах

```bash
# 1. Остановите сервис
sudo systemctl stop bg-remove-bot

# 2. Откатите код
cd /opt/bg-remove-bot
sudo -u www-data git reset --hard HEAD~1

# 3. Откатите миграции (если нужно)
sudo -u www-data /opt/bg-remove-bot/venv/bin/alembic downgrade -1

# 4. Запустите сервис
sudo systemctl start bg-remove-bot
```

## Резервное копирование

### Автоматический backup PostgreSQL

Создайте скрипт `/opt/bg-remove-bot/backup.sh`:

```bash
#!/bin/bash

BACKUP_DIR="/opt/bg-remove-bot/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/bg_removal_bot_$DATE.sql"

# Создайте директорию если нет
mkdir -p $BACKUP_DIR

# Создайте backup
sudo -u postgres pg_dump bg_removal_bot > $BACKUP_FILE

# Сжатие
gzip $BACKUP_FILE

# Удалите старые backup'ы (старше 30 дней)
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete

echo "Backup created: $BACKUP_FILE.gz"
```

Сделайте исполняемым:
```bash
sudo chmod +x /opt/bg-remove-bot/backup.sh
```

### Настройка cron для автоматического backup

```bash
sudo crontab -e
```

Добавьте строку (backup каждый день в 3:00 AM):
```
0 3 * * * /opt/bg-remove-bot/backup.sh >> /var/log/bg-remove-bot-backup.log 2>&1
```

### Восстановление из backup

```bash
# 1. Остановите бота
sudo systemctl stop bg-remove-bot

# 2. Удалите текущую БД (ОСТОРОЖНО!)
sudo -u postgres psql -c "DROP DATABASE bg_removal_bot;"

# 3. Создайте новую БД
sudo -u postgres psql -c "CREATE DATABASE bg_removal_bot OWNER bgremove_user;"

# 4. Восстановите из backup
gunzip < /opt/bg-remove-bot/backups/bg_removal_bot_YYYYMMDD_HHMMSS.sql.gz | \
  sudo -u postgres psql bg_removal_bot

# 5. Запустите бота
sudo systemctl start bg-remove-bot
```

## Troubleshooting

### Бот не запускается

```bash
# Проверьте логи
sudo journalctl -u bg-remove-bot -n 50

# Проверьте статус
sudo systemctl status bg-remove-bot

# Проверьте конфигурацию .env
sudo -u www-data cat /opt/bg-remove-bot/.env

# Проверьте права доступа
ls -la /opt/bg-remove-bot/
```

### Ошибки базы данных

```bash
# Проверьте подключение к БД
sudo -u www-data psql -U bgremove_user -d bg_removal_bot -h localhost

# Проверьте статус PostgreSQL
sudo systemctl status postgresql

# Проверьте логи PostgreSQL
sudo tail -f /var/log/postgresql/postgresql-*-main.log
```

### Бот не отвечает на сообщения

1. Проверьте токен бота в `.env`
2. Проверьте, что бот запущен: `sudo systemctl status bg-remove-bot`
3. Проверьте логи: `sudo journalctl -u bg-remove-bot -f`
4. Проверьте интернет-соединение сервера

### Высокое потребление памяти

```bash
# Проверьте использование памяти
sudo systemctl status bg-remove-bot | grep Memory

# Перезапустите сервис
sudo systemctl restart bg-remove-bot

# Настройте swap (если нет)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### Проблемы с OpenRouter API

1. Проверьте API ключ в `.env`
2. Проверьте баланс на openrouter.ai
3. Проверьте логи на наличие ошибок API: `sudo journalctl -u bg-remove-bot | grep -i openrouter`

## Безопасность

### Рекомендации

1. **Используйте сильные пароли** для PostgreSQL
2. **Ограничьте доступ** к серверу через SSH (только по ключам)
3. **Настройте fail2ban** для защиты от брутфорса
4. **Регулярно обновляйте** систему и зависимости
5. **Настройте мониторинг** (например, через Prometheus + Grafana)
6. **Проверяйте логи** на подозрительную активность

### Дополнительная защита

```bash
# Установите fail2ban
sudo apt install fail2ban

# Настройте SSH (только ключи)
sudo nano /etc/ssh/sshd_config
# PasswordAuthentication no
# PubkeyAuthentication yes

sudo systemctl restart ssh

# Настройте автоматические обновления безопасности
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

## Поддержка

Если у вас возникли проблемы:

1. Проверьте логи: `sudo journalctl -u bg-remove-bot -f`
2. Проверьте документацию в README.md
3. Создайте issue в GitHub репозитории

---

**Версия документа**: 1.0
**Дата обновления**: 2024-01-12
