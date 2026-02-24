#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────
# MaktabKhoonehFarm — One-shot server deployer
# Tested on Ubuntu 24.04 (1 CPU · 1 GB RAM)
# ──────────────────────────────────────────────

REPO_URL="${1:-https://github.com/MohamadHoseinSabour/MaktabKhoonehFarm.git}"
INSTALL_DIR="/opt/acms"

echo "═══════════════════════════════════════════"
echo "  ACMS Server Deploy"
echo "═══════════════════════════════════════════"
echo

# ─── 1. Swap (skip if one already exists) ───
echo "[1/5] Setting up swap..."
if swapon --show | grep -q '/swapfile'; then
  echo "    → Swap already active, skipping."
else
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "    → 2 GB swap created."
fi

# ─── 2. System packages ───
echo "[2/5] Installing system packages..."
apt-get update -qq
apt-get install -y -qq git redis-server python3-venv curl >/dev/null

# Start Redis
systemctl enable --now redis-server

# Node.js 20 via NodeSource
if ! command -v node &>/dev/null; then
  echo "    → Installing Node.js 20..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null 2>&1
  apt-get install -y -qq nodejs >/dev/null
fi
echo "    → node $(node --version)  npm $(npm --version)"

# ─── 3. Clone repository ───
echo "[3/5] Cloning repository..."
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "    → Repo already exists, pulling latest..."
  cd "$INSTALL_DIR"
  git pull --ff-only
else
  git clone "$REPO_URL" "$INSTALL_DIR"
  cd "$INSTALL_DIR"
fi

# ─── 4. Create .env ───
echo "[4/5] Configuring .env..."
SERVER_IP=$(hostname -I | awk '{print $1}')
if [ ! -f .env ]; then
  cp .env.example .env
  sed -i "s|NEXT_PUBLIC_API_BASE_URL=.*|NEXT_PUBLIC_API_BASE_URL=http://${SERVER_IP}:8000|" .env
  sed -i "s|ALLOWED_HOSTS=.*|ALLOWED_HOSTS=localhost,127.0.0.1,${SERVER_IP}|" .env
  echo "    → .env created with IP=$SERVER_IP"
else
  echo "    → .env already exists, skipping."
fi

# ─── 5. Run the app ───
echo "[5/5] Starting services..."
chmod +x run_latest.sh
bash run_latest.sh
