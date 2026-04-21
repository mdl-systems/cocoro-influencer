#!/bin/bash
# install_frontend.sh: Next.js フロントエンドの初回セットアップ (cocoro-render-01)
# 使い方: sudo ./install_frontend.sh
#
# 実行内容:
#   1. Node.js 22 LTS インストール (NodeSource)
#   2. frontend/ の npm install + build
#   3. cocoro-studio.service を systemd に登録・起動
set -e

APP_DIR=/home/cocoro-influencer
FRONTEND_DIR="$APP_DIR/frontend"
SERVICE_SRC="$APP_DIR/deploy/cocoro-studio.service"
SERVICE_DEST=/etc/systemd/system/cocoro-studio.service

echo "=== cocoro-studio フロントエンド初回セットアップ ==="

# ─── 1. Node.js インストール確認 ──────────────────────
if ! command -v node &>/dev/null; then
    echo "[INSTALL] Node.js 22 LTS をインストール中..."
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y nodejs
    echo "[OK] Node.js $(node -v) インストール完了"
else
    echo "[SKIP] Node.js $(node -v) は既にインストール済み"
fi

# ─── 2. frontend/ ビルド ──────────────────────────────
echo "[BUILD] frontend/ をビルド中..."
cd "$FRONTEND_DIR"
npm ci --prefer-offline
npm run build
echo "[OK] フロントエンドビルド完了"

# ─── 3. systemd サービス登録 ─────────────────────────
echo "[SERVICE] cocoro-studio.service を登録中..."
cp "$SERVICE_SRC" "$SERVICE_DEST"
systemctl daemon-reload
systemctl enable cocoro-studio
systemctl start cocoro-studio
sleep 2

if curl -sf http://localhost:3000 >/dev/null; then
    echo "[OK] フロントエンド起動確認 OK"
else
    echo "[WARN] http://localhost:3000 応答なし - ログを確認してください"
    journalctl -u cocoro-studio -n 30 --no-pager
fi

echo ""
echo "=== セットアップ完了 ==="
echo "フロントエンド: http://192.168.50.48:3000"
echo "API:            http://192.168.50.48:8082"
