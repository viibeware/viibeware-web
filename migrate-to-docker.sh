#!/bin/bash
# ──────────────────────────────────────────────────────────────
# migrate-to-docker.sh
# Migrates an existing bare-metal viibeware install to Docker.
#
# Prerequisites:
#   - Docker and Docker Compose installed
#   - The old install at /opt/viibeware (or set OLD_INSTALL below)
#   - This script run from the project directory containing
#     docker-compose.yml
# ──────────────────────────────────────────────────────────────

set -euo pipefail

OLD_INSTALL="${1:-/opt/viibeware}"
COMPOSE_PROJECT="viibeware"

echo "═══════════════════════════════════════════════════════"
echo "  viibeware — Migration to Docker"
echo "═══════════════════════════════════════════════════════"
echo ""

# ── Validate old install ─────────────────────────────────────
if [ ! -f "$OLD_INSTALL/app.py" ]; then
  echo "✗ Could not find existing install at $OLD_INSTALL"
  echo "  Usage: $0 /path/to/old/viibeware"
  exit 1
fi

echo "✓ Found existing install at $OLD_INSTALL"

# ── Stop old systemd service ─────────────────────────────────
if systemctl is-active --quiet viibeware-web 2>/dev/null; then
  echo "→ Stopping viibeware-web systemd service..."
  sudo systemctl stop viibeware-web
  sudo systemctl disable viibeware-web
  echo "✓ Service stopped and disabled"
else
  echo "→ No active systemd service found (skipping)"
fi

# ── Create .env if it doesn't exist ──────────────────────────
if [ ! -f .env ]; then
  echo "→ Creating .env from .env.example..."
  cp .env.example .env
  # Generate a real secret key
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  sed -i "s/change-me-to-a-random-string/$SECRET/" .env
  echo "✓ Generated .env with new secret key"
  echo "  ⚠ Review .env and set your admin credentials"
else
  echo "→ .env already exists (keeping)"
fi

# ── Start containers to create volumes ───────────────────────
echo "→ Starting containers to initialize volumes..."
docker compose up -d
sleep 3

# ── Copy content.json into the data volume ───────────────────
if [ -f "$OLD_INSTALL/data/content.json" ]; then
  echo "→ Migrating content.json..."
  docker compose cp "$OLD_INSTALL/data/content.json" viibeware-web:/app/data/content.json
  echo "✓ Content data migrated"
else
  echo "→ No content.json found, will use defaults"
fi

# ── Copy uploaded images into the uploads volume ─────────────
if [ -d "$OLD_INSTALL/static/img" ]; then
  echo "→ Migrating uploaded images..."
  # Copy all image files (skip CSS/JS dirs)
  for f in "$OLD_INSTALL/static/img"/*; do
    if [ -f "$f" ]; then
      docker compose cp "$f" "viibeware-web:/app/static/img/$(basename "$f")"
    fi
  done
  echo "✓ Images migrated"
fi

# ── Restart to pick up migrated data ─────────────────────────
echo "→ Restarting container..."
docker compose restart
sleep 2

# ── Verify ───────────────────────────────────────────────────
if docker compose ps | grep -q "Up"; then
  echo ""
  echo "═══════════════════════════════════════════════════════"
  echo "  ✓ Migration complete!"
  echo ""
  echo "  Site:  http://$(hostname -I | awk '{print $1}'):8899"
  echo "  Admin: http://$(hostname -I | awk '{print $1}'):8899/admin"
  echo ""
  echo "  Your old install at $OLD_INSTALL is untouched."
  echo "  Once you've verified everything works, you can"
  echo "  remove it and the old systemd service file:"
  echo ""
  echo "    sudo rm -rf $OLD_INSTALL"
  echo "    sudo rm /etc/systemd/system/viibeware-web.service"
  echo "    sudo systemctl daemon-reload"
  echo "═══════════════════════════════════════════════════════"
else
  echo "✗ Container doesn't appear to be running."
  echo "  Check: docker compose logs viibeware-web"
  exit 1
fi
