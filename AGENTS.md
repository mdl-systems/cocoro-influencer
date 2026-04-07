# cocoro-influencer 開発エージェントガイド

## プロジェクト概要
企業専属AIインフルエンサー動画自動生成システム
実写風アバターが企業を紹介する動画をブラウザから生成する

## 本番サーバー環境
- OS: Debian 13.3
- IP: 192.168.50.77 (社内LAN)
- Port: 8082
- Python: 3.12 (venv: .venv)
- GPU: RTX 4090 24GB (CUDA 12.4)
- LLM: Ollama + Qwen2.5:32B (localhost:11434)
- パッケージ管理: uv

## アーキテクチャ
- FastAPI (src/api/) → REST API
- src/modules/ → 台本/音声/動画/リップシンク
- ui/index.html → Web UI
- Ollama → ローカルLLM台本生成
- Kling AI API → 動画生成
- Sync.so API → リップシンク

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
- ui/index.html: Web UI (vanilla JS)
- config/.env: APIキー (gitignore対象)
- requirements.txt: Python依存関係

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
