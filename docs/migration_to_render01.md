# cocoro-influencer 統合移行計画
# cocoro-render-01 (192.168.50.48) への集約

## 移行後アーキテクチャ

```
cocoro-render-01 (192.168.50.48) ← 全サービス集約
├── GPU: RTX PRO 6000 Blackwell 96GB (メイン)
├── GPU: RTX 4060 Ti 8GB (補助)
├── RAM: 256GB
├── CPU: Ryzen 9 9950X3D
└── Storage: /data 3.7TB

サービス一覧:
├── cocoro-influencer API  → ポート 8082
├── Ollama (Qwen2.5:32b)  → ポート 11434
├── Style-Bert-VITS2       → ポート 5000
├── Wan2.1 推論 (subprocess /data/venv/wan2)
├── Wav2Lip リップシンク (/opt/wav2lip)
└── InstantID (/mnt/models/InstantID または /data/models/InstantID)
```

## Phase 1: Ollama インストール ← 作業中

```bash
# render-01 で実行
curl -fsSL https://ollama.com/install.sh | sh
systemctl enable ollama && systemctl start ollama

# モデル pull (19GB - 時間がかかる)
OLLAMA_MODELS=/data/ollama ollama pull qwen2.5:32b-instruct-q4_K_M
# ※ /data に保存することで /data の余裕を活用
```

### Ollamaモデル保存場所の変更
```bash
# systemd override でモデルパスを /data に変更
mkdir -p /etc/systemd/system/ollama.service.d/
cat > /etc/systemd/system/ollama.service.d/override.conf << 'EOF'
[Service]
Environment="OLLAMA_MODELS=/data/ollama/models"
EOF
systemctl daemon-reload && systemctl restart ollama
```

## Phase 2: Style-Bert-VITS2 セットアップ

モデルは /mnt/models/Style-Bert-VITS2 に既存 (NFS経由)

```bash
# 新しい venv を /data に作成
python3 -m venv /data/venv/sbv2
source /data/venv/sbv2/bin/activate
pip install torch==2.4.0 torchaudio==2.4.0 --index-url https://download.pytorch.org/whl/cu124
pip install style-bert-vits2

# systemdサービス作成
cat > /etc/systemd/system/style-bert-vits2.service << 'EOF'
[Unit]
Description=Style-Bert-VITS2 TTS Server
After=network.target

[Service]
Type=simple
ExecStart=/data/venv/sbv2/bin/python /mnt/models/Style-Bert-VITS2/server_editor.py \
  --port 5000 --model_assets_root /mnt/models/Style-Bert-VITS2/model_assets
WorkingDirectory=/mnt/models/Style-Bert-VITS2
Restart=always

[Install]
WantedBy=multi-user.target
EOF
systemctl enable style-bert-vits2
systemctl start style-bert-vits2
```

## Phase 3: cocoro-influencer .env 更新

```bash
cat > /home/cocoro-influencer/config/.env << 'EOF'
# cocoro-render-01 統合設定
KLING_ACCESS_KEY=AkC8t8pgkgNN3CKArp8nm4pJMQTJYGTe
KLING_SECRET_KEY=BeQmbaDmrKHMrdkGkQCp4Ff9D9bKyGJy
LIPSYNC_API_KEY=sk-DfODkRwrRLSxNIvPW6EOcQ.ethK83BEuqyUp5GDHkM2NlS8PwrwM0iH

# ローカルサービス (移行後)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:32b-instruct-q4_K_M
LLM_PROVIDER=ollama

# ポート変更 (8082に統一)
APP_HOST=0.0.0.0
APP_PORT=8082

# Wav2Lip (render-01固有)
WAV2LIP_PYTHON=/data/models/Wav2Lip/venv/bin/python
WAV2LIP_DIR=/data/models/Wav2Lip

# Wan2.1
WAN2_PYTHON=/data/venv/wan2/bin/python
WAN2_MODEL_PATH=/data/models/Wan2.1/I2V-14B-480P

# 出力
OUTPUT_DIR=/mnt/data/outputs
EOF
```

## Phase 4: AGENTS.md 更新

サーバー情報を render-01 に統一:
- IP: 192.168.50.48
- Port: 8082
- OLLAMA: localhost:11434
- SBV2: localhost:5000

## Phase 5 (任意): NFS依存を解除

render-01 をcompletely独立させるためにモデルを /data にコピー:
```bash
rsync -av /mnt/models/InstantID /data/models/
rsync -av /mnt/models/antelopev2 /data/models/
rsync -av /mnt/models/Wav2Lip /data/models/
# RealVisXL は巨大 (20GB) なので必要に応じて
```

## 進捗チェックリスト

- [x] Wan2.1 モデルDL完了 (77GB /data/models/Wan2.1)
- [x] Wav2Lip venv セットアップ完了 (/data/models/Wav2Lip/venv)
- [x] Ollama インストール & Qwen2.5:32b pull 完了
- [x] Style-Bert-VITS2 セットアップ完了 (systemd: style-bert-vits2.service)
- [x] .env 更新 (localhost に切り替え完了)
- [x] ポート 8082 に統一
- [x] E2Eテスト (台本→音声→動画) 完了
- [x] AGENTS.md 更新
- [ ] server-01 シャットダウン or 別用途

## アクセス URL (移行後)

| サービス | URL |
|---------|-----|
| cocoro-influencer UI | http://192.168.50.48:8082/studio |
| Ollama API | http://192.168.50.48:11434 |
| Style-Bert-VITS2 | http://192.168.50.48:5000 |
