#!/bin/bash

# Update script for Background Removal Telegram Bot
# This script automates the update process

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
INSTALL_DIR="/opt/bg-remove-bot"
SERVICE_NAME="bg-remove-bot"
APP_USER="www-data"
BACKUP_DIR="$INSTALL_DIR/backups"

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

create_backup() {
    print_info "Creating backup..."

    mkdir -p "$BACKUP_DIR"
    DATE=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/bg_removal_bot_$DATE.sql"

    sudo -u postgres pg_dump bg_removal_bot > "$BACKUP_FILE"
    gzip "$BACKUP_FILE"

    print_info "Backup created: $BACKUP_FILE.gz"
}

stop_service() {
    print_info "Stopping service..."
    systemctl stop "$SERVICE_NAME"
    print_info "Service stopped"
}

update_code() {
    print_info "Updating code..."

    cd "$INSTALL_DIR"
    sudo -u $APP_USER git fetch --all

    # Show what will be updated
    print_warning "Changes to be pulled:"
    sudo -u $APP_USER git log HEAD..origin/main --oneline || true

    if [[ "$AUTO_UPDATE" != "yes" ]]; then
        read -p "Continue with update? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_warning "Update cancelled"
            systemctl start "$SERVICE_NAME"
            exit 0
        fi
    fi

    sudo -u $APP_USER git pull

    print_info "Code updated"
}

update_dependencies() {
    print_info "Updating dependencies..."

    cd "$INSTALL_DIR"
    sudo -u $APP_USER "$INSTALL_DIR/venv/bin/pip" install -r requirements.txt --upgrade

    print_info "Dependencies updated"
}

run_migrations() {
    print_info "Running database migrations..."

    cd "$INSTALL_DIR"
    sudo -u $APP_USER "$INSTALL_DIR/venv/bin/alembic" upgrade head

    print_info "Migrations completed"
}

start_service() {
    print_info "Starting service..."
    systemctl start "$SERVICE_NAME"
    sleep 2

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_info "Service started successfully!"
        systemctl status "$SERVICE_NAME" --no-pager -l
    else
        print_error "Service failed to start!"
        print_error "Check logs: journalctl -u $SERVICE_NAME -n 50"
        exit 1
    fi
}

cleanup_old_backups() {
    print_info "Cleaning up old backups (>30 days)..."
    find "$BACKUP_DIR" -name "*.sql.gz" -mtime +30 -delete || true
    print_info "Cleanup completed"
}

show_logs() {
    print_info "Recent logs:"
    journalctl -u "$SERVICE_NAME" -n 20 --no-pager
}

main() {
    print_info "Starting update of Background Removal Telegram Bot"

    check_root
    create_backup
    stop_service
    update_code
    update_dependencies
    run_migrations
    start_service
    cleanup_old_backups
    show_logs

    echo ""
    print_info "==================================================="
    print_info "Update completed successfully!"
    print_info "==================================================="
    echo ""
    print_info "Monitor logs with: journalctl -u $SERVICE_NAME -f"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --auto|-a)
            AUTO_UPDATE="yes"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -a, --auto    Skip confirmation prompts"
            echo "  -h, --help    Show this help message"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

main
