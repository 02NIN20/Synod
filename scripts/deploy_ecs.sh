#!/usr/bin/env bash
# Deploy Synod to Alibaba Cloud ECS
# Usage: ./scripts/deploy_ecs.sh <ecs-ip> [ssh-password]

set -euo pipefail

ECS_IP="${1:?Usage: $0 <ecs-ip> [ssh-password]}"
SSH_PASS="${2:-}"
REMOTE_DIR="/root/synod"
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"

echo "=== Deploying Synod to Alibaba Cloud ECS ($ECS_IP) ==="

# Rsync source code (excluding venv, .git, env, cache)
rsync -avz --delete \
  --exclude=.git \
  --exclude=.venv \
  --exclude=.env \
  --exclude=.pytest_cache \
  -e "sshpass -p '$SSH_PASS' ssh $SSH_OPTS" \
  . "root@$ECS_IP:$REMOTE_DIR/"

# Restart container on ECS
if [ -n "$SSH_PASS" ]; then
  sshpass -e ssh $SSH_OPTS root@"$ECS_IP" \
    "cd $REMOTE_DIR && docker compose down && docker compose up -d --build"
else
  ssh $SSH_OPTS root@"$ECS_IP" \
    "cd $REMOTE_DIR && docker compose down && docker compose up -d --build"
fi

echo "=== Done. API running at http://$ECS_IP:8000 ==="
echo "Health: curl http://$ECS_IP:8000/health"
