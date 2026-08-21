#!/bin/bash
# EC2 Deployment Script for Prognosis Classifier
# This script sets up both backend (FastAPI) and frontend (Vite/React) on EC2

set -e  # Exit on error

echo "=========================================="
echo "Prognosis Classifier - EC2 Deployment"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_DIR="/opt/prognosis-classifier"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend/interactive-dashboard-hub"
BACKEND_USER="prognosis"
SERVICE_NAME="prognosis-api"
NGINX_SITE="prognosis-classifier"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${GREEN}Step 1: Installing system dependencies...${NC}"
# Update package list
apt-get update -y

# Install Python 3.13 and pip
apt-get install -y python3.13 python3.13-venv python3-pip python3.13-dev

# Install Node.js 20.x (LTS)
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# Install nginx
apt-get install -y nginx

# Install git and other utilities
apt-get install -y git build-essential curl

# Install MongoDB client tools (optional, for debugging)
apt-get install -y mongodb-database-tools || echo "MongoDB tools not available, skipping"

echo -e "${GREEN}Step 2: Creating application user...${NC}"
# Create user if doesn't exist
if ! id "$BACKEND_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$BACKEND_USER"
    echo "User $BACKEND_USER created"
else
    echo "User $BACKEND_USER already exists"
fi

echo -e "${GREEN}Step 3: Setting up application directory...${NC}"
mkdir -p "$APP_DIR"
chown -R "$BACKEND_USER:$BACKEND_USER" "$APP_DIR"

# If code is already cloned, update it; otherwise assume code was synced from local
if [ -d "$APP_DIR/.git" ]; then
    echo "Repository already exists with git metadata, pulling latest from remote..."
    cd "$APP_DIR"
    sudo -u "$BACKEND_USER" git pull
else
    echo -e "${YELLOW}No .git directory found in $APP_DIR${NC}"
    echo -e "${YELLOW}Assuming application code was copied/synced from your local machine.${NC}"
    echo "Using existing code at $APP_DIR (no git operations)."
    cd "$APP_DIR"
fi

echo -e "${GREEN}Step 4: Setting up Python backend...${NC}"
cd "$BACKEND_DIR"

# Create virtual environment
if [ ! -d "venv" ]; then
    sudo -u "$BACKEND_USER" python3.13 -m venv venv
fi

# Activate venv and install dependencies
sudo -u "$BACKEND_USER" bash -c "source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"

# Create .env file if it doesn't exist
if [ ! -f "$BACKEND_DIR/.env" ]; then
    echo -e "${YELLOW}Creating .env file template...${NC}"
    sudo -u "$BACKEND_USER" cat > "$BACKEND_DIR/.env" << 'EOF'
MONGO_URI=mongodb+srv://healthflex-production:FUvgMqSppKigmKHK@healthflex-prod.su93nwo.mongodb.net/stance-dashboard?retryWrites=true&w=majority
MONGO_DB=stance-dashboard
GOOGLE_CLOUD_PROJECT=stance-ai
GOOGLE_APPLICATION_CREDENTIALS=/opt/prognosis-classifier/backend/stance-ai-8919b7295fb6.json
GOOGLE_CLOUD_LOCATION=us-central1
EOF
    echo -e "${YELLOW}Please edit $BACKEND_DIR/.env with your actual credentials${NC}"
fi

# Ensure credentials file exists
if [ ! -f "$BACKEND_DIR/stance-ai-8919b7295fb6.json" ]; then
    echo -e "${YELLOW}WARNING: Google credentials file not found at $BACKEND_DIR/stance-ai-8919b7295fb6.json${NC}"
    echo "Please upload your service account JSON file"
fi

echo -e "${GREEN}Step 5: Setting up systemd service for backend...${NC}"
cat > "/etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=Prognosis Classifier FastAPI Backend
After=network.target

[Service]
Type=simple
User=$BACKEND_USER
WorkingDirectory=$BACKEND_DIR
Environment="PATH=$BACKEND_DIR/venv/bin"
ExecStart=$BACKEND_DIR/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8013
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo -e "${GREEN}Step 6: Building frontend...${NC}"
cd "$FRONTEND_DIR"

# Install Node dependencies
sudo -u "$BACKEND_USER" npm install

# Build for production
sudo -u "$BACKEND_USER" npm run build

echo -e "${GREEN}Step 7: Configuring nginx...${NC}"
cat > "/etc/nginx/sites-available/${NGINX_SITE}" << EOF
# Upstream for FastAPI backend
upstream backend {
    server 127.0.0.1:8013;
}

# WebSocket upstream (for clinical agent)
upstream backend_ws {
    server 127.0.0.1:8013;
}

server {
    listen 80;
    server_name _;  # Replace with your domain name

    # Frontend static files
    root $FRONTEND_DIR/dist;
    index index.html;

    # Frontend routes (SPA)
    location / {
        try_files \$uri \$uri/ /index.html;
    }

    # Backend API
    location /api/ {
        proxy_pass http://backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # WebSocket for clinical agent
    location /ws {
        proxy_pass http://backend_ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;
    }

    # Health check
    location /health {
        proxy_pass http://backend/health;
        access_log off;
    }
}
EOF

# Enable site
ln -sf "/etc/nginx/sites-available/${NGINX_SITE}" "/etc/nginx/sites-enabled/${NGINX_SITE}"

# Remove default nginx site if it exists
rm -f /etc/nginx/sites-enabled/default

# Test nginx config
nginx -t

# Restart nginx
systemctl restart nginx

echo -e "${GREEN}Step 8: Configuring firewall (UFW)...${NC}"
# Allow SSH, HTTP, HTTPS
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable || echo "UFW not active, skipping"

echo ""
echo -e "${GREEN}=========================================="
echo "Deployment Complete!"
echo "==========================================${NC}"
echo ""
echo "Backend API: http://$(curl -s ifconfig.me)/api"
echo "Frontend: http://$(curl -s ifconfig.me)/"
echo "WebSocket: ws://$(curl -s ifconfig.me)/ws"
echo ""
echo "Service status:"
echo "  Backend: systemctl status ${SERVICE_NAME}"
echo "  Nginx: systemctl status nginx"
echo ""
echo "Logs:"
echo "  Backend: journalctl -u ${SERVICE_NAME} -f"
echo "  Nginx: tail -f /var/log/nginx/error.log"
echo ""
echo -e "${YELLOW}IMPORTANT:${NC}"
echo "1. Edit $BACKEND_DIR/.env with your actual credentials"
echo "2. Upload your Google service account JSON to $BACKEND_DIR/stance-ai-8919b7295fb6.json"
echo "3. Update nginx config with your domain name (replace 'server_name _;')"
echo "4. For HTTPS, install certbot: apt-get install certbot python3-certbot-nginx && certbot --nginx"
echo ""
