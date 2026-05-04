#!/bin/bash
# deploy.sh: cocoro-influencer デプロイスクリプト (cocoro-render-01専用)
# 使い方: ./deploy.sh
#
# 初回のみ事前実行が必要:
#   sudo ./install_frontend.sh  (Node.js + systemd cocoro-studio.service 登録)
set -e

VENV=/data/venv/cocoro
APP_DIR=/home/cocoro-influencer
FRONTEND_DIR="$APP_DIR/frontend"
API_SERVICE=cocoro-influencer
STUDIO_SERVICE=cocoro-studio

echo "=== cocoro-influencer デプロイ開始 ==="

cd "$APP_DIR"
# ローカル変更があっても強制的にリモートへ追従する
git fetch origin main
git stash || true            # ローカル変更を退避（なければ無視）
git reset --hard origin/main # リモートの最新に強制同期
git stash drop 2>/dev/null || true  # 退避内容は不要なので破棄
chmod +x "$APP_DIR/deploy.sh" "$APP_DIR/install_frontend.sh" 2>/dev/null || true
echo "[OK] git pull 完了"

# ─── 1. Python バックエンド ────────────────────────────
"$VENV/bin/pip" install -q -r requirements.txt
echo "[OK] pip install 完了"

systemctl restart "$API_SERVICE"
sleep 8

if curl -sf http://localhost:8082/health > /dev/null; then
    echo "[OK] API ヘルスチェック OK (port 8082)"
else
    echo "[NG] API ヘルスチェック失敗"
    journalctl -u "$API_SERVICE" -n 50 --no-pager
    exit 1
fi

# ─── 2. Next.js フロントエンド ─────────────────────────
if systemctl is-enabled --quiet "$STUDIO_SERVICE" 2>/dev/null; then
    echo "[BUILD] Next.js フロントエンドをビルド中..."
    cd "$FRONTEND_DIR"
    npm install
    npm run build
    echo "[OK] ビルド完了"

    systemctl restart "$STUDIO_SERVICE"
    sleep 3

    if curl -sf http://localhost:3000 > /dev/null; then
        echo "[OK] フロントエンド ヘルスチェック OK (port 3000)"
    else
        echo "[WARN] フロントエンド http://localhost:3000 応答なし"
        journalctl -u "$STUDIO_SERVICE" -n 30 --no-pager
    fi
else
    echo "[SKIP] cocoro-studio.service 未登録 → ./install_frontend.sh を先に実行してください"
fi

# ─── 完了サマリー ──────────────────────────────────────
echo ""
systemctl status "$API_SERVICE" --no-pager -l
echo ""
echo "=== デプロイ完了 ==="
echo "API:         http://192.168.50.48:8082"
echo "Vanilla UI:  http://192.168.50.48:8082/studio"
echo "Next.js UI:  http://192.168.50.48:3000"
echo "API Doc:     http://192.168.50.48:8082/docs"
