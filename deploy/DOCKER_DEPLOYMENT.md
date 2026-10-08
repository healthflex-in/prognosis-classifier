# Docker deployment on the existing server

Use this workflow for the Docker/Caddy setup. `ec2_deploy.sh` and
`ec2_manage.sh` are legacy systemd/nginx scripts, not this deployment workflow.

## One-time setup

1. Recover `backend/LLM/prognosis/prognosis_agent.py` and
   `prognosis_langchain_agent.py` from the known-working deployment. Check any
   sibling imports (such as `prognosis_cli.py`) and include those sources too.
   Review and commit the original Python files. The old `prognosis/` ignore rule
   excluded the nested source directory; it is now restricted to `/prognosis/`.
   These missing files cannot be reconstructed by the deployment script.
2. Provision `backend/.env.prod` (or `.env.dev`) on the server, with the correct
   MongoDB connection/database and Google project. Set
   `GOOGLE_APPLICATION_CREDENTIALS=/app/stance-ai-8919b7295fb6.json`.
3. Provision the valid Google service-account JSON once. The default host path
   remains `backend/stance-ai-8919b7295fb6.json`. To keep it outside checkouts,
   put `PROD_GOOGLE_CREDENTIALS_FILE=/etc/prognosis/prod-service-account.json`
   in the project-root `.env` used by Compose. Dev supports
   `DEV_GOOGLE_CREDENTIALS_FILE` separately. This is a host path; do not change
   the container credentials path above. Ensure the deploying user can read it.
   Do not commit or bake credential files into images.
4. Docker Compose must support `up --wait` and long bind mounts.

## Routine deployment

After updating the checked-out code on the server:

```bash
cd /var/www/prod/prognosis-classifier
bash deploy/deploy.sh prod
```

Use `bash deploy/deploy.sh dev` from the dev checkout for dev only. The script
does not pull code or select a branch: it deploys the current checkout. It
uses only the selected environment's `.env` file and targets its two services.

| Environment | Compose file | Environment file | Host ports |
| --- | --- | --- | --- |
| Dev | `docker-compose.dev.yml` | `backend/.env.dev` | 8013 / 8014 |
| Prod | `docker-compose.prod.yml` | `backend/.env.prod` | 8015 / 8016 |

The combined `docker-compose.yml` has been removed. Always select one file;
neither deployment requires the other environment's `.env` file. Service and
container names and port mappings are unchanged, so Caddy needs no changes.
Use the same checkout and Compose project identity as your existing deployment.
Do not add `--remove-orphans` when both environments share a Compose project.

For direct Compose use (bypasses the deployment script's authentication check):

```bash
# Dev only
docker compose -f docker-compose.dev.yml up -d --build --wait
docker compose -f docker-compose.dev.yml logs -f --tail=50

# Prod only
docker compose -f docker-compose.prod.yml up -d --build --wait
docker compose -f docker-compose.prod.yml logs -f --tail=50
```

The script checks source files/syntax and resolved credential paths, builds the
images, checks Google authentication in disposable containers, and only then
recreates selected services and waits up to 120 seconds for health checks.
Checks do not start change-stream listeners, generate AI output or write patient
records. Failed preflight/build checks leave existing containers running.
Health failure after replacement exits unsuccessfully; automatic rollback is
not implemented. Authentication success does not prove Vertex model permission
or end-to-end generation success.

Missing credential files are rejected rather than created as directories.
The image build also rejects missing prognosis source. Neither environment files
nor service-account keys are included in the build context.

## Optional local-to-server sync

```bash
SSH_KEY=/path/to/deploy-key.pem \
EC2_HOST=ubuntu@your-server \
REMOTE_APP=/var/www/prod/prognosis-classifier \
bash deploy/push_to_ec2.sh prod
```

This requires an existing server checkout and provisioned secrets. It syncs code
without deleting files, keeps environment/credential files on the server, and
invokes the same checked deployment command. SSH host-key verification remains
enabled. It does not install Docker, rewrite credentials, remove old containers,
or restart the other environment.
Only the selected Compose file is synced. A legacy combined Compose file may
remain on an rsync-managed server; the deployment script never uses it.

## Verification

```bash
python3 -m unittest discover -s deploy -p 'test_*.py'
bash -n deploy/deploy.sh deploy/push_to_ec2.sh
```

Tests use a fake Docker executable and temporary fixture files; they do not
contact a server. An additional test uses the real Compose parser with dummy
environment values to verify both files independently (no Docker daemon needed).
The Google authentication check happens during real deployment.
