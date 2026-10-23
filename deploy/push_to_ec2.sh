#!/usr/bin/env bash
# Sync code from this checkout, then invoke the same checked server deployment.
# SSH_KEY=/path/key.pem EC2_HOST=ubuntu@host REMOTE_APP=/var/www/prod/prognosis-classifier \
#   bash deploy/push_to_ec2.sh prod
set -euo pipefail

target="${1:-}"
case "$target" in dev|prod) ;; *) echo 'Usage: bash deploy/push_to_ec2.sh dev|prod' >&2; exit 2 ;; esac
: "${SSH_KEY:?Set SSH_KEY to your SSH private key path}"
: "${EC2_HOST:?Set EC2_HOST to user@hostname}"
: "${REMOTE_APP:?Set REMOTE_APP to the existing server checkout}"
[[ -f "$SSH_KEY" ]] || { echo 'SSH_KEY is not a file' >&2; exit 1; }
# Restrict remote arguments so SSH/rsync cannot reinterpret shell syntax.
[[ "$REMOTE_APP" =~ ^/[a-zA-Z0-9_./-]+$ && "$EC2_HOST" =~ ^[a-zA-Z0-9_@.-]+$ ]] || {
  echo 'Use a simple absolute REMOTE_APP path and user@host EC2_HOST.' >&2; exit 1;
}
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$project_root/backend/scripts/deployment_check.py" --source-only

# No automatic deletion, environment rewrites or credential upload.
# Keep the server's credentials and .env.dev/.env.prod provisioned separately.
printf -v rsync_ssh 'ssh -i %q' "$SSH_KEY"
ssh -i "$SSH_KEY" "$EC2_HOST" "test -d '$REMOTE_APP'"
rsync -az -e "$rsync_ssh" \
  --exclude='.env' --exclude='.env.*' --exclude='stance-ai-*.json' \
  --exclude='aaa.json' --exclude='*.pem' --exclude='*.log' \
  --exclude='__pycache__/' --exclude='*.pyc' --exclude='.venv/' --exclude='venv/' \
  "$project_root/backend/" "$EC2_HOST:$REMOTE_APP/backend/"
rsync -az -e "$rsync_ssh" "$project_root/docker-compose.$target.yml" "$EC2_HOST:$REMOTE_APP/"
rsync -az -e "$rsync_ssh" --include='*.sh' --exclude='*' \
  "$project_root/deploy/" "$EC2_HOST:$REMOTE_APP/deploy/"
ssh -i "$SSH_KEY" "$EC2_HOST" "cd '$REMOTE_APP' && bash deploy/deploy.sh '$target'"
