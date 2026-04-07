# cocoro-influencer — AGENTS.md

## プロジェクト概要
企業専属AIインフルエンサー動画生成システム。
実写風リアルアバターが企業を紹介する動画を自動生成する。

## サーバー環境
- OS: Debian 13.3
- IP: 192.168.50.77
- Port: 8082
- Python: 3.12
- GPU: RTX 4090 (CUDA 12.4)
- LLM: Ollama + Qwen2.5:32B (localhost:11434)

## 開発フロー
1. Antigravityでコード編集
2. `git commit & push to main`
3. サーバーで `./deploy.sh` を実行

## デプロイ
```bash
ssh root@192.168.50.77
cd /home/cocoro-influencer
./deploy.sh
```

## 重要ファイル
- `src/api/main.py` — FastAPIメインアプリ
- `src/api/routes/pipeline.py` — 動画生成パイプライン
- `ui/index.html` — Web UI
- `config/.env` — APIキー設定（gitignore済み）

## アーキテクチャルール
- AIモデルは `src/engines/` の `BaseEngine` サブクラスとして実装
- `EngineManager` がGPUメモリ一元管理（同時ロード禁止）
- 入力/出力は全てファイルパス（`Path` オブジェクト）
- CLIエントリポイントは `src/cli.py`（typer）

## コーディングルール
- 応急処置禁止・根本修正のみ
- 日本語コメント必須
- 型ヒント必須（Pydantic または dataclass）
- エンジンは `load` / `unload` / `generate` を実装すること

## 使わないもの（意図的）
- ComfyUI（不要な中間レイヤー）
- Celery/Redis（GPU 1台で不要）
- PostgreSQL/SQLAlchemy（Phase 3まで不要）
- Docker（uv仮想環境で十分）
