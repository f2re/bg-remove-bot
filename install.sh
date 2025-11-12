#!/bin/bash

# Installation script for Background Removal Telegram Bot
# This script automates the production deployment process

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/bg-remove-bot"
APP_USER="www-data"
SERVICE_NAME="bg-remove-bot"
DB_NAME="bg_removal_bot"
DB_USER="bgremove_user"

# Functions
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root"
        exit 1
    fi
}

install_dependencies() {
    print_info "Installing system dependencies..."
    apt update
    apt install -y \
        python3.11 \
        python3.11-venv \
        python3-pip \
        postgresql \
        postgresql-contrib \
        git \
        build-essential \
        libpq-dev \
        || {
            print_error "Failed to install dependencies"
            exit 1
        }
    print_info "Dependencies installed successfully"
}

setup_database() {
    print_info "Setting up PostgreSQL database..."

    # Generate random password if not provided
    if [[ -z "$DB_PASSWORD" ]]; then
        DB_PASSWORD=$(openssl rand -base64 32)
        print_warning "Generated database password: $DB_PASSWORD"
        print_warning "Please save this password! It will be needed for .env file"
    fi

    # Create user and database
    sudo -u postgres psql <<EOF
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = '$DB_USER') THEN
        CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';
    END IF;
END
\$\$;

SELECT 'CREATE DATABASE $DB_NAME OWNER $DB_USER'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\gexec

GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
EOF

    print_info "Database setup completed"
    echo "DB_PASSWORD=$DB_PASSWORD" >> /tmp/bg-remove-bot-credentials.txt
}

clone_repository() {
    print_info "Cloning repository..."

    if [[ -z "$REPO_URL" ]]; then
        print_error "REPO_URL not set. Please set it with: export REPO_URL=<your-repo-url>"
        exit 1
    fi

    mkdir -p "$INSTALL_DIR"
    chown $APP_USER:$APP_USER "$INSTALL_DIR"

    if [[ -d "$INSTALL_DIR/.git" ]]; then
        print_warning "Repository already exists. Pulling latest changes..."
        sudo -u $APP_USER git -C "$INSTALL_DIR" pull
    else
        sudo -u $APP_USER git clone "$REPO_URL" "$INSTALL_DIR"
    fi

    print_info "Repository cloned successfully"
}

setup_venv() {
    print_info "Setting up Python virtual environment..."

    cd "$INSTALL_DIR"
    sudo -u $APP_USER python3.11 -m venv venv
    sudo -u $APP_USER "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
    sudo -u $APP_USER "$INSTALL_DIR/venv/bin/pip" install -r requirements.txt

    print_info "Virtual environment setup completed"
}

configure_env() {
    print_info "Configuring environment variables..."

    if [[ ! -f "$INSTALL_DIR/.env" ]]; then
        sudo -u $APP_USER cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"

        # Set database URL
        sed -i "s|DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME|" "$INSTALL_DIR/.env"

        print_warning "Please edit $INSTALL_DIR/.env and fill in the required values:"
        print_warning "  - BOT_TOKEN"
        print_warning "  - ADMIN_IDS"
        print_warning "  - OPENROUTER_API_KEY"
        print_warning "  - ROBOKASSA_* credentials"

        read -p "Press Enter after editing .env file..."
    else
        print_warning ".env file already exists. Skipping..."
    fi
}

run_migrations() {
    print_info "Running database migrations..."

    cd "$INSTALL_DIR"
    sudo -u $APP_USER "$INSTALL_DIR/venv/bin/alembic" upgrade head

    print_info "Migrations completed"
}

setup_systemd() {
    print_info "Setting up systemd service..."

    cp "$INSTALL_DIR/bg-remove-bot.service" "/etc/systemd/system/$SERVICE_NAME.service"
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"

    print_info "Systemd service configured"
}

start_service() {
    print_info "Starting service..."

    systemctl start "$SERVICE_NAME"
    sleep 2

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_info "Service started successfully!"
        systemctl status "$SERVICE_NAME" --no-pager
    else
        print_error "Service failed to start. Check logs with: journalctl -u $SERVICE_NAME -n 50"
        exit 1
    fi
}

show_summary() {
    echo ""
    print_info "==================================================="
    print_info "Installation completed successfully!"
    print_info "==================================================="
    echo ""
    print_info "Service name: $SERVICE_NAME"
    print_info "Installation directory: $INSTALL_DIR"
    print_info "Database: $DB_NAME"
    print_info "Database user: $DB_USER"
    echo ""
    print_warning "IMPORTANT: Credentials saved to /tmp/bg-remove-bot-credentials.txt"
    print_warning "Please save them and delete this file!"
    echo ""
    print_info "Useful commands:"
    echo "  - View logs:        sudo journalctl -u $SERVICE_NAME -f"
    echo "  - Restart service:  sudo systemctl restart $SERVICE_NAME"
    echo "  - Stop service:     sudo systemctl stop $SERVICE_NAME"
    echo "  - Service status:   sudo systemctl status $SERVICE_NAME"
    echo ""
}

# Main installation flow
main() {
    print_info "Starting installation of Background Removal Telegram Bot"

    check_root
    install_dependencies
    setup_database
    clone_repository
    setup_venv
    configure_env
    run_migrations
    setup_systemd
    start_service
    show_summary
}

# Show usage if no REPO_URL
if [[ -z "$REPO_URL" ]]; then
    echo "Usage: REPO_URL=<your-repo-url> bash install.sh"
    echo ""
    echo "Optional environment variables:"
    echo "  DB_PASSWORD  - PostgreSQL password (auto-generated if not set)"
    echo ""
    echo "Example:"
    echo "  REPO_URL=https://github.com/user/bg-remove-bot.git bash install.sh"
    exit 1
fi

# Run main installation
main
