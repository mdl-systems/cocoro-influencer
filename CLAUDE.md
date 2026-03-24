# cocoro-influencer

## プロジェクト概要
企業専属AIインフルエンサー生成システム。
実写風リアルアバターが企業を紹介する動画を自動生成する。
cocoro-OSとは別サービス。将来的にcocoro-agentとして統合予定。

## リポジトリ
https://github.com/mdl-systems/cocoro-influencer

## 技術スタック
- Python 3.12 + uv
- AI: Diffusers/PyTorch直接呼び出し (RTX 5090, 32GB VRAM)
  - FLUX.2 + LoRA: アバター画像生成
  - Wan 2.6 I2V: シネマティック動画
  - EchoMimic: リップシンクトーキングヘッド
  - VOICEVOX: 日本語TTS
- CLI: typer
- 動画合成: FFmpeg (ffmpeg-python)
- ジョブ履歴: SQLite (sqlite3標準)

## 使わないもの（意図的）
- ComfyUI (不要な中間レイヤー)
- Celery/Redis (GPU 1台で不要)
- PostgreSQL/SQLAlchemy (Phase 3まで不要)
- FastAPI (Phase 3まで不要)
- Docker (uv仮想環境で十分)

## アーキテクチャルール
- AIモデルは src/engines/ のBaseEngineサブクラスとして実装
- EngineManagerがGPUメモリ一元管理（同時ロード禁止）
- 入力/出力は全てファイルパス (Pathオブジェクト)
- CLIは src/cli.py (typer)

## ルール
- 応急処置禁止・根本修正のみ
- 日本語コメント必須
- 型ヒント必須 (Pydanticまたはdataclass)
- エンジンはload/unload/generateを実装

## ディレクトリ構造
```
cocoro-influencer/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── .gitignore
│
├── src/
│   ├── __init__.py
│   ├── engines/                 # AIモデルエンジン (核心)
│   │   ├── __init__.py
│   │   ├── base.py              # BaseEngine ABC
│   │   ├── manager.py           # EngineManager
│   │   ├── flux_engine.py       # FLUX.2 + LoRA → PNG
│   │   ├── wan_engine.py        # Wan 2.6 I2V → MP4
│   │   ├── echomimic_engine.py  # リップシンク → MP4
│   │   └── voice_engine.py      # TTS → WAV
│   │
│   ├── pipeline/                # パイプライン制御
│   │   ├── __init__.py
│   │   ├── orchestrator.py      # 全体制御
│   │   └── compositor.py        # FFmpeg動画合成
│   │
│   ├── cli.py                   # typer CLIエントリポイント
│   │
│   └── agent/                   # cocoro-OS統合 (Phase 5)
│       ├── __init__.py
│       └── interface.py         # インターフェース定義のみ
│
├── models/                      # AIモデルウェイト (.gitignore)
├── loras/                       # 顧客別LoRA (.gitignore)
├── outputs/                     # 生成物 (.gitignore)
│
├── tests/
│   ├── test_engines.py
│   └── test_pipeline.py
│
└── scripts/
    └── download_models.py       # モデル一括ダウンロード
```

## cocoro-OS統合情報 (Phase 5用)
- COCORO_CORE_URL: http://192.168.50.92:8001
- API_KEY: cocoro-2026
- agent_type: worker | agent_role: specialist
- schema: v7 | cocoro-net: 172.30.0.0/24

## パイプライン概要
```
台本生成 (LLM API)
  │
  ├─→ 音声合成 (VOICEVOX / ElevenLabs)
  │
  ├─→ アバター画像生成 (FLUX.2 + LoRA)
  │     │
  │     ├─→ パターンA: 画像 + 音声 → トーキングヘッド (EchoMimic)
  │     │
  │     └─→ パターンB: 画像 + プロンプト → シネマティック (Wan 2.6 I2V)
  │
  └─→ 合成 (FFmpeg): クリップ結合 + BGM + テロップ
```
