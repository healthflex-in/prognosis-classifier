#!/usr/bin/env bash
# Run on the server: bash deploy/deploy.sh prod (or dev).
set -euo pipefail

target="${1:-}"
case "$target" in dev|prod) ;; *) echo 'Usage: bash deploy/deploy.sh dev|prod' >&2; exit 2 ;; esac
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
services=("backend-$target" "recommendation-$target")
compose=(docker compose -f "$project_root/docker-compose.$target.yml")

# Each Compose file reads only its own environment file.
selected_env="$project_root/backend/.env.$target"
[[ -f "$selected_env" ]] || { echo "Missing $selected_env" >&2; exit 1; }

python3 backend/scripts/deployment_check.py --source-only
"${compose[@]}" version >/dev/null

# Inspect resolved paths without printing the rendered config (it has secrets).
# This also rejects an existing directory, which create_host_path alone cannot.
"${compose[@]}" config --format json | python3 -c '
import json, pathlib, sys
config = json.load(sys.stdin)
for name in sys.argv[1:]:
    service = config["services"][name]
    env = service.get("environment", {})
    if not env.get("MONGO_URI") or not env.get("MONGO_DB"):
        sys.exit(f"{name}: missing MONGO_URI or MONGO_DB")
    credentials = env.get("GOOGLE_APPLICATION_CREDENTIALS")
    mount = next((v for v in service.get("volumes", []) if v.get("target") == credentials), None)
    if not mount or not pathlib.Path(mount["source"]).is_file():
        sys.exit(f"{name}: credential mount must be an existing JSON file. Check the host path and GOOGLE_APPLICATION_CREDENTIALS.")
print("Environment and credential file checks passed.")
' "${services[@]}"

# Build and check a disposable container before replacing running services.
"${compose[@]}" build "${services[@]}"
for service in "${services[@]}"; do
  "${compose[@]}" run --rm --no-deps -T --entrypoint python "$service" scripts/deployment_check.py
done
"${compose[@]}" up -d --no-deps --wait --wait-timeout 120 "${services[@]}"
"${compose[@]}" ps "${services[@]}"
echo "Deployment complete: $target services are healthy."
