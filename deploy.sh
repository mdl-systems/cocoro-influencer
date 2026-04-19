#!/bin/bash
# deploy.sh: cocoro-influencer デプロイスクリプト (cocoro-render-01専用)
# 使い方: ./deploy.sh
set -e

VENV=/data/venv/cocoro
APP_DIR=/home/cocoro-influencer
SERVICE=cocoro-influencer

echo "=== cocoro-influencer デプロイ開始 ==="

cd "$APP_DIR"
git pull origin main
echo "[OK] git pull 完了"

"$VENV/bin/pip" install -q -r requirements.txt
echo "[OK] pip install 完了"

systemctl restart "$SERVICE"
sleep 3

if curl -sf http://localhost:8082/health > /dev/null; then
    echo "[OK] ヘルスチェック OK"
    systemctl status "$SERVICE" --no-pager -l
    echo ""
    echo "=== デプロイ完了 ==="
    echo "API: http://192.168.50.48:8082"
    echo "UI:  http://192.168.50.48:8082/studio"
    echo "Doc: http://192.168.50.48:8082/docs"
else
    echo "[NG] ヘルスチェック失敗"
    journalctl -u "$SERVICE" -n 50 --no-pager
    exit 1
fi
