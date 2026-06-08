#!/bin/bash
# ============================================================
# Local → EC2 deploy (Docker)
# Usage: ./deploy/push_to_ec2.sh
# ============================================================

set -e

PEM="/Users/chris/Healthflex/Prognosis-validator/deploy/prognosis_classifier.pem"
EC2_HOST="ubuntu@ec2-3-110-133-84.ap-south-1.compute.amazonaws.com"
REMOTE_APP="/opt/prognosis-classifier"

GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
log() { echo -e "${GREEN}▶ $1${NC}"; }
err() { echo -e "${RED}✗ $1${NC}"; exit 1; }

[ -f "$PEM" ] || err "PEM not found: $PEM"
chmod 400 "$PEM"

SSH="ssh -i $PEM -o StrictHostKeyChecking=no"
RSYNC="rsync -az --progress -e \"ssh -i $PEM -o StrictHostKeyChecking=no\""
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── 1. Ensure remote dir ──────────────────────────────────────
log "Preparing remote directory..."
$SSH $EC2_HOST "sudo mkdir -p $REMOTE_APP && sudo chown ubuntu:ubuntu $REMOTE_APP"

# ── 2. Install Docker if missing ─────────────────────────────
log "Ensuring Docker is installed..."
$SSH $EC2_HOST bash << 'DOCKER_INSTALL'
if ! command -v docker &>/dev/null; then
  echo "Installing Docker..."
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker ubuntu
  sudo systemctl enable docker
  sudo systemctl start docker
  echo "✔ Docker installed"
else
  echo "✔ Docker already installed"
fi
if ! command -v docker-compose &>/dev/null && ! docker compose version &>/dev/null 2>&1; then
  sudo apt-get install -y -q docker-compose-plugin
fi
DOCKER_INSTALL

# ── 3. Sync code ──────────────────────────────────────────────
log "Syncing code..."

eval "$RSYNC \
  --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='.env' \
  --exclude='*.pem' --exclude='*.log' \
  --exclude='prognosis_report_*.txt' --exclude='.DS_Store' \
  $PROJECT_ROOT/backend/ $EC2_HOST:$REMOTE_APP/backend/"

eval "$RSYNC \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' \
  --include='*.py' --include='docker-compose.yml' --exclude='*' \
  $PROJECT_ROOT/ $EC2_HOST:$REMOTE_APP/"

log "Code synced."

# ── 4. Fix .env + build + restart ────────────────────────────
log "Building and starting containers..."

$SSH $EC2_HOST REMOTE_APP=$REMOTE_APP bash << 'REMOTE'
set -e
cd $REMOTE_APP

# .env is never synced (contains secrets) — it must already exist on the host.
# Fail fast with an actionable message instead of a cryptic compose env_file error.
if [ ! -f backend/.env ]; then
  echo "✗ backend/.env is missing on the host ($REMOTE_APP/backend/.env)."
  echo "  It is intentionally excluded from rsync. Copy it up first, then re-run:"
  echo "    scp -i <pem> backend/.env <host>:$REMOTE_APP/backend/.env"
  exit 1
fi

# Fix credentials path in .env
sed -i "s|GOOGLE_APPLICATION_CREDENTIALS=.*|GOOGLE_APPLICATION_CREDENTIALS=/app/stance-ai-8919b7295fb6.json|" backend/.env
echo "✔ Fixed credentials path"

# Remove any legacy non-compose container holding port 8013 (e.g. an old
# 'prognosis-api' started via `docker run`). Otherwise `docker compose up`
# fails with "Bind for :::8013 failed: port is already allocated".
for c in $(docker ps -aq --filter "name=prognosis-api"); do
  echo "Removing legacy container $c (frees port 8013)..."
  docker rm -f "$c" || true
done

# Build and restart
docker compose build --pull
docker compose up -d --remove-orphans

# Verify — wait and confirm the container is actually stable, not crash-looping
# (a crashing container briefly reports "Up" before restarting).
cid=$(docker compose ps -q backend)
ok=0
for i in $(seq 1 10); do
  sleep 3
  state=$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || echo missing)
  restarts=$(docker inspect -f '{{.RestartCount}}' "$cid" 2>/dev/null || echo 0)
  echo "  check $i: status=$state restarts=$restarts"
  if [ "$state" = "running" ] && [ "$restarts" -eq 0 ]; then
    ok=1; break
  fi
  if [ "$state" = "restarting" ] || [ "$restarts" -gt 0 ]; then
    ok=0; break
  fi
done

if [ "$ok" = "1" ]; then
  echo "✔ Container stable:"
  docker compose ps
else
  echo "✗ Container failed or is crash-looping — logs:"
  docker compose logs --tail=40 backend
  exit 1
fi
REMOTE

log "Done — http://ec2-3-110-133-84.ap-south-1.compute.amazonaws.com"
log "API  — http://ec2-3-110-133-84.ap-south-1.compute.amazonaws.com:8013"
log "WS   — ws://ec2-3-110-133-84.ap-south-1.compute.amazonaws.com/ws"
