#!/bin/bash
# Quick management script for Prognosis Classifier on EC2

set -e

APP_DIR="/opt/prognosis-classifier"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend/interactive-dashboard-hub"
SERVICE_NAME="prognosis-api"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

show_help() {
    echo "Prognosis Classifier - EC2 Management Script"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  status      - Show status of all services"
    echo "  restart     - Restart backend and nginx"
    echo "  logs        - Show backend logs (follow mode)"
    echo "  update      - Pull latest code and rebuild"
    echo "  rebuild     - Rebuild frontend only"
    echo "  stop        - Stop all services"
    echo "  start       - Start all services"
    echo "  health      - Check health endpoints"
    echo ""
}

status() {
    echo -e "${GREEN}Service Status:${NC}"
    echo ""
    systemctl status "${SERVICE_NAME}" --no-pager -l || true
    echo ""
    systemctl status nginx --no-pager -l || true
    echo ""
    echo -e "${GREEN}Port Status:${NC}"
    netstat -tlnp | grep -E ':(80|443|8013)' || true
}

restart() {
    echo -e "${YELLOW}Restarting services...${NC}"
    sudo systemctl restart "${SERVICE_NAME}"
    sudo systemctl restart nginx
    echo -e "${GREEN}Services restarted${NC}"
    status
}

logs() {
    echo -e "${GREEN}Backend logs (Ctrl+C to exit):${NC}"
    sudo journalctl -u "${SERVICE_NAME}" -f
}

update() {
    echo -e "${YELLOW}Updating application...${NC}"
    cd "$APP_DIR"
    
    # Pull latest code
    git pull
    
    # Restart backend
    sudo systemctl restart "${SERVICE_NAME}"
    
    # Rebuild frontend
    cd "$FRONTEND_DIR"
    npm install
    npm run build
    
    # Reload nginx
    sudo systemctl reload nginx
    
    echo -e "${GREEN}Update complete!${NC}"
}

rebuild() {
    echo -e "${YELLOW}Rebuilding frontend...${NC}"
    cd "$FRONTEND_DIR"
    npm install
    npm run build
    sudo systemctl reload nginx
    echo -e "${GREEN}Frontend rebuilt${NC}"
}

stop() {
    echo -e "${YELLOW}Stopping services...${NC}"
    sudo systemctl stop "${SERVICE_NAME}"
    sudo systemctl stop nginx
    echo -e "${GREEN}Services stopped${NC}"
}

start() {
    echo -e "${YELLOW}Starting services...${NC}"
    sudo systemctl start "${SERVICE_NAME}"
    sudo systemctl start nginx
    echo -e "${GREEN}Services started${NC}"
    status
}

health() {
    echo -e "${GREEN}Health Checks:${NC}"
    echo ""
    echo "Backend API:"
    curl -s http://localhost:8013/health | jq . || curl -s http://localhost:8013/health
    echo ""
    echo ""
    echo "Frontend:"
    curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" http://localhost/
    echo ""
    echo "Nginx:"
    curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" http://localhost/api/health
}

# Main command handler
case "${1:-help}" in
    status)
        status
        ;;
    restart)
        restart
        ;;
    logs)
        logs
        ;;
    update)
        update
        ;;
    rebuild)
        rebuild
        ;;
    stop)
        stop
        ;;
    start)
        start
        ;;
    health)
        health
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        show_help
        exit 1
        ;;
esac
