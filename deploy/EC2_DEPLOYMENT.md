# EC2 Deployment Guide for Prognosis Classifier

This guide walks you through deploying both the frontend and backend to a single EC2 instance.

## Prerequisites

1. **EC2 Instance** (Ubuntu 22.04 LTS or later recommended)
   - Minimum: t3.medium (2 vCPU, 4 GB RAM)
   - Recommended: t3.large (2 vCPU, 8 GB RAM) or larger
   - Security Group: Allow inbound on ports 22 (SSH), 80 (HTTP), 443 (HTTPS)

2. **Domain name** (optional, but recommended for HTTPS)

3. **Access to your repository**:
   - GitHub: `https://github.com/healthflex-in/prognosis-classifier.git`
   - Or have your code ready to upload

## Quick Deployment

### Option 1: Automated Script (Recommended)

1. **SSH into your EC2 instance**:
   ```bash
   ssh -i your-key.pem ubuntu@your-ec2-ip
   ```

2. **Clone the repository** (or upload the deployment script):
   ```bash
   git clone https://github.com/healthflex-in/prognosis-classifier.git /opt/prognosis-classifier
   # OR upload deploy/ec2_deploy.sh to the server
   ```

3. **Run the deployment script**:
   ```bash
   cd /opt/prognosis-classifier
   sudo bash deploy/ec2_deploy.sh
   ```

4. **Follow the prompts** and configure your `.env` file.

### Option 2: Manual Step-by-Step

See the detailed steps below.

## Manual Deployment Steps

### 1. Connect to EC2

```bash
ssh -i your-key.pem ubuntu@your-ec2-ip
```

### 2. Install System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y python3.13 python3.13-venv python3-pip python3.13-dev
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
sudo apt-get install -y nodejs nginx git build-essential
```

### 3. Clone Repository

```bash
sudo mkdir -p /opt/prognosis-classifier
sudo git clone https://github.com/healthflex-in/prognosis-classifier.git /opt/prognosis-classifier
sudo chown -R ubuntu:ubuntu /opt/prognosis-classifier
```

### 4. Set Up Backend

```bash
cd /opt/prognosis-classifier/backend

# Create virtual environment
python3.13 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create .env file
nano .env
```

**Add to `.env`**:
```bash
MONGO_URI=mongodb+srv://healthflex-production:FUvgMqSppKigmKHK@healthflex-prod.su93nwo.mongodb.net/stance-dashboard?retryWrites=true&w=majority
MONGO_DB=stance-dashboard
GOOGLE_CLOUD_PROJECT=stance-ai
GOOGLE_APPLICATION_CREDENTIALS=/opt/prognosis-classifier/backend/stance-ai-8919b7295fb6.json
GOOGLE_CLOUD_LOCATION=us-central1
```

**Upload Google credentials**:
```bash
# From your local machine:
scp -i your-key.pem backend/stance-ai-8919b7295fb6.json ubuntu@your-ec2-ip:/opt/prognosis-classifier/backend/
```

### 5. Create Systemd Service for Backend

```bash
sudo nano /etc/systemd/system/prognosis-api.service
```

**Add**:
```ini
[Unit]
Description=Prognosis Classifier FastAPI Backend
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/prognosis-classifier/backend
Environment="PATH=/opt/prognosis-classifier/backend/venv/bin"
ExecStart=/opt/prognosis-classifier/backend/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8013
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable and start**:
```bash
sudo systemctl daemon-reload
sudo systemctl enable prognosis-api
sudo systemctl start prognosis-api
sudo systemctl status prognosis-api
```

### 6. Build Frontend

```bash
cd /opt/prognosis-classifier/frontend/interactive-dashboard-hub

# Install dependencies
npm install

# Build for production
npm run build
```

**Create `.env.production`** (if needed):
```bash
VITE_API_URL=http://your-ec2-ip/api
# OR if using domain:
# VITE_API_URL=https://your-domain.com/api
```

**Rebuild**:
```bash
npm run build
```

### 7. Configure Nginx

```bash
sudo nano /etc/nginx/sites-available/prognosis-classifier
```

**Add**:
```nginx
upstream backend {
    server 127.0.0.1:8013;
}

upstream backend_ws {
    server 127.0.0.1:8013;
}

server {
    listen 80;
    server_name your-domain.com;  # Replace with your domain or EC2 IP

    # Frontend
    root /opt/prognosis-classifier/frontend/interactive-dashboard-hub/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # Backend API
    location /api/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket
    location /ws {
        proxy_pass http://backend_ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;
    }

    # Health check
    location /health {
        proxy_pass http://backend/health;
        access_log off;
    }
}
```

**Enable site**:
```bash
sudo ln -s /etc/nginx/sites-available/prognosis-classifier /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

### 8. Configure Firewall

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 9. Set Up HTTPS (Optional but Recommended)

```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

## Verification

1. **Check backend**:
   ```bash
   curl http://localhost:8013/health
   # Should return: {"status":"healthy","service":"Clinical Dashboard API"}
   ```

2. **Check frontend**:
   ```bash
   curl http://localhost/
   # Should return HTML
   ```

3. **Check services**:
   ```bash
   sudo systemctl status prognosis-api
   sudo systemctl status nginx
   ```

4. **View logs**:
   ```bash
   # Backend logs
   sudo journalctl -u prognosis-api -f

   # Nginx logs
   sudo tail -f /var/log/nginx/error.log
   sudo tail -f /var/log/nginx/access.log
   ```

## Updating the Application

### Update Code

```bash
cd /opt/prognosis-classifier
git pull origin dev-1  # or your branch

# Restart backend
sudo systemctl restart prognosis-api

# Rebuild frontend if needed
cd frontend/interactive-dashboard-hub
npm install
npm run build
sudo systemctl reload nginx
```

### Update Environment Variables

```bash
nano /opt/prognosis-classifier/backend/.env
sudo systemctl restart prognosis-api
```

## Troubleshooting

### Backend not starting

```bash
# Check logs
sudo journalctl -u prognosis-api -n 50

# Check if port is in use
sudo netstat -tlnp | grep 8013

# Test manually
cd /opt/prognosis-classifier/backend
source venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8013
```

### Frontend not loading

```bash
# Check nginx config
sudo nginx -t

# Check nginx logs
sudo tail -f /var/log/nginx/error.log

# Verify dist folder exists
ls -la /opt/prognosis-classifier/frontend/interactive-dashboard-hub/dist
```

### WebSocket not connecting

- Ensure nginx config has the `/ws` location block
- Check backend is running: `curl http://localhost:8013/health`
- Verify firewall allows port 80/443

## Architecture

```
Internet
   |
   v
Nginx (Port 80/443)
   |
   +---> / (Frontend static files from dist/)
   |
   +---> /api/* (Proxy to FastAPI on port 8013)
   |
   +---> /ws (WebSocket proxy to FastAPI on port 8013)
```

## Security Considerations

1. **Use HTTPS**: Always set up SSL/TLS with Let's Encrypt
2. **Firewall**: Only open necessary ports (22, 80, 443)
3. **Environment Variables**: Never commit `.env` files
4. **Service Account**: Restrict Google Cloud service account permissions
5. **MongoDB**: Use strong passwords and IP whitelisting
6. **Regular Updates**: Keep system packages updated

## Monitoring

### Set up basic monitoring

```bash
# Install monitoring tools (optional)
sudo apt-get install htop iotop

# Set up log rotation
sudo nano /etc/logrotate.d/prognosis-api
```

Add:
```
/var/log/prognosis-api/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}
```

## Backup

### Backup MongoDB data

```bash
# Install MongoDB tools
sudo apt-get install mongodb-database-tools

# Create backup script
nano /opt/prognosis-classifier/backup.sh
```

Add:
```bash
#!/bin/bash
BACKUP_DIR="/opt/backups/prognosis"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

# Backup classifications
mongodump --uri="your-mongo-uri" --db=stance-dashboard --collection=classification --out="$BACKUP_DIR/classification_$DATE"

# Backup prognosis
mongodump --uri="your-mongo-uri" --db=stance-dashboard --collection=prognosis --out="$BACKUP_DIR/prognosis_$DATE"

# Clean old backups (keep last 7 days)
find "$BACKUP_DIR" -type d -mtime +7 -exec rm -rf {} +
```

Make executable:
```bash
chmod +x /opt/prognosis-classifier/backup.sh

# Add to crontab (daily at 2 AM)
crontab -e
# Add: 0 2 * * * /opt/prognosis-classifier/backup.sh
```
