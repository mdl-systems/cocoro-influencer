# cocoro-influencer 開発エージェントガイド

## プロジェクト概要
企業専属AIインフルエンサー動画自動生成システム
実写風アバターが企業を紹介する動画をブラウザから生成する

## 本番サーバー環境 (cocoro-render-01)
- OS: Debian 13.3
- IP: 192.168.50.48 (社内LAN)
- Port: 8082
- Python: 3.12 (venv: /data/venv/cocoro/)
- GPU: RTX PRO 6000 Blackwell 96GB (CUDA 12.6)
- RAM: 256GB / CPU: Ryzen 9 9950X3D
- LLM: Ollama + Qwen2.5:32B (localhost:11434)
- TTS: Style-Bert-VITS2 (localhost:5000, /home/Style-Bert-VITS2/)
- ストレージ: /data 3.7TB
- パッケージ管理: uv

## アーキテクチャ
- FastAPI (src/api/) → REST API
- src/engines/ → AIエンジン (BaseEngineサブクラス)
- src/pipeline/ → orchestrator + compositor
- ui/index.html → Web UI
- Ollama → ローカルLLM台本生成 (localhost:11434)
- Kling AI API → talking_head 動画生成
- Wan2.1 I2V → cinematic 動画生成 (ローカル /data/models/Wan2.1/)
- Wav2Lip → リップシンク (/data/models/Wav2Lip/)
- InstantID → ポーズ別アバター生成 (/data/models/InstantID/)
- Style-Bert-VITS2 → 日本語TTS (localhost:5000)

## 開発フロー
1. Antigravityでコード編集
2. git commit & push origin main
3. サーバーでデプロイ:
   ssh root@192.168.50.77
   cd /home/cocoro-influencer && ./deploy.sh

## 重要ファイル
- src/api/main.py: FastAPIエントリーポイント
- src/api/routes/pipeline.py: 動画生成パイプライン
- src/api/routes/jobs.py: ジョブ管理
- src/api/routes/avatars.py: アバター生成・アップロード
- src/pipeline/orchestrator.py: パイプライン制御
- src/pipeline/compositor.py: FFmpeg動画合成
- scripts/generate_wan_video.py: Wan2.1サブプロセス実行スクリプト
- scripts/generate_instantid_poses.py: InstantIDポーズ生成スクリプト
- ui/index.html: Web UI (vanilla JS)
- config/.env: APIキー (gitignore対象)

## サーバーパス一覧 (render-01)
- AIモデル:        /data/models/
- Wan2.1:          /data/models/Wan2.1/I2V-14B-480P
- Wav2Lip:         /data/models/Wav2Lip/
- InstantID:       /data/models/InstantID/
- 出力:            /data/outputs/
- アプリ:          /home/cocoro-influencer/
- Style-Bert-VITS2:/home/Style-Bert-VITS2/
- Wan2 venv:       /data/venv/wan2/bin/python
- Wav2Lip venv:    /data/models/Wav2Lip/venv/bin/python
- InstantID venv:  /data/models/InstantID/venv/bin/python

## コーディングルール
- Python 3.12+
- 非同期処理: async/await
- 型ヒント必須
- ログ: logging モジュール使用
- コメント: 日本語OK

## 注意事項
- config/.env はgitにコミットしない
- outputs/ はgitにコミットしない
- VRAM使用量に注意（RTX 4090 24GB）
- エンジンの同時ロード禁止（EngineManager経由で管理）
