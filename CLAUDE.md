# cocoro-influencer

## プロジェクト概要
企業専属AIインフルエンサー動画自動生成システム。
実写風リアルアバターが企業を紹介する動画をブラウザから生成する。
cocoro-OSとは別サービス。将来的にcocoro-agentとして統合予定。

## リポジトリ
https://github.com/mdl-systems/cocoro-influencer

## 本番サーバー環境 (cocoro-render-01)
- OS: Debian / IP: 192.168.50.48 / Port: 8082
- GPU: RTX PRO 6000 Blackwell 96GB (CUDA 12.6)
- Python: 3.12 (venv: /data/venv/cocoro/)
- LLM: Ollama + Qwen2.5:32B (localhost:11434)
- TTS: Style-Bert-VITS2 (localhost:5000)
- ストレージ: /data 3.7TB / パッケージ管理: uv

## 技術スタック
- Python 3.12 + uv
- AI:
  - FLUX.1-dev: アバター画像生成 (LoRA対応)
  - Wan2.1 I2V-14B-480P: シネマティック & talking_head 動画生成 (subprocess)
  - Wav2Lip: リップシンク (subprocess, /data/models/Wav2Lip/)
  - InstantID: ポーズ別アバター生成 (subprocess)
- TTS: Style-Bert-VITS2 (localhost:5000 HTTP API)
- LLM: Ollama / Qwen2.5:32B (localhost:11434)
- FastAPI: REST API ゲートウェイ
- 動画合成: FFmpeg (subprocess直接呼び出し)
- 台本: Ollama / OpenAI互換 / Gemini / Anthropic マルチプロバイダー

## 使わないもの（意図的）
- ComfyUI (不要な中間レイヤー)
- Celery/Redis (GPU 1台で不要)
- PostgreSQL/SQLAlchemy (Phase 3まで不要)
- Docker (uv仮想環境で十分)

## アーキテクチャルール
- AIモデルは src/engines/ の BaseEngine サブクラスとして実装
- EngineManager が GPU メモリ一元管理（同時ロード禁止）
- 入力/出力は全てファイルパス (Path オブジェクト)
- WanEngine / Wav2Lip / InstantID は subprocess 方式（独自 venv）
- FastAPI サーバーは src/api/server.py (create_app) をエントリポイントとする

## ルール
- 応急処置禁止・根本修正のみ
- 日本語コメント必須
- 型ヒント必須 (Pydantic または dataclass)
- エンジンは load / unload / generate を実装
- コードのデッドコードを残さない

## ディレクトリ構造
```
cocoro-influencer/
├── CLAUDE.md
├── AGENTS.md
├── README.md
├── pyproject.toml
├── deploy.sh
├── .gitignore
│
├── src/
│   ├── __init__.py
│   ├── cli.py                   # typer/Pipeline CLIエントリポイント
│   │
│   ├── engines/                 # AIモデルエンジン (核心)
│   │   ├── base.py              # BaseEngine ABC
│   │   ├── manager.py           # EngineManager
│   │   ├── flux_engine.py       # FLUX.1-dev + LoRA → PNG
│   │   ├── wan_engine.py        # Wan2.1 I2V → MP4 (直接ロード用)
│   │   ├── echomimic_engine.py  # EchoMimic (将来用、現在はWav2Lipを使用)
│   │   ├── voice_engine.py      # Style-Bert-VITS2 → WAV
│   │   └── script_engine.py    # LLM台本生成 (Ollama/Gemini/Anthropic)
│   │
│   ├── pipeline/                # パイプライン制御
│   │   ├── orchestrator.py      # 全体制御 (Wan2.1+Wav2Lip subprocess)
│   │   ├── compositor.py        # FFmpeg動画合成 (SAR不一致対応)
│   │   └── script_parser.py     # 台本YAMLパーサー
│   │
│   ├── api/                     # FastAPI
│   │   ├── server.py            # FastAPIアプリ定義 (create_app)
│   │   ├── main.py              # uvicorn起動エントリポイント
│   │   └── routes/              # ルート分割 (pipeline / jobs / avatars)
│   │
│   └── agent/                   # cocoro-OS統合 (Phase 5)
│       └── interface.py
│
├── scripts/
│   ├── generate_wan_video.py    # Wan2.1 subprocess実行スクリプト
│   ├── wav2lip_fullbody.py      # Wav2Lip fullbody lipsync
│   ├── generate_instantid_poses.py  # InstantIDポーズ生成
│   └── download_models.py       # モデル一括ダウンロード
│
├── config/
│   └── .env                     # APIキー等 (gitignore対象)
│
├── models/                      # AIモデルウェイト (.gitignore) ※サーバーは/data/models/
├── outputs/                     # 生成物 (.gitignore) ※サーバーは/data/outputs/
├── ui/                          # バニラJS Web UI (index.html)
├── frontend/                    # Next.js 15 ダッシュボード (開発中)
└── tests/
    └── (テストファイル)
```

## サーバーパス一覧 (render-01)
- AIモデル:         /data/models/
- Wan2.1:           /data/models/Wan2.1/I2V-14B-480P
- Wan2.1 venv:      /data/venv/wan2/bin/python
- Wav2Lip:          /data/models/Wav2Lip/
- Wav2Lip venv:     /data/models/Wav2Lip/venv/bin/python
- InstantID:        /data/models/InstantID/
- InstantID venv:   /data/models/InstantID/venv/bin/python
- 出力:             /data/outputs/
- アプリ:           /home/cocoro-influencer/
- Style-Bert-VITS2: /home/Style-Bert-VITS2/
- メイン venv:      /data/venv/cocoro/

## パイプライン概要
```
台本生成 (ScriptEngine → Ollama:11434)
  │
  ├─→ 音声合成 (VoiceEngine → Style-Bert-VITS2:5000)
  │
  ├─→ アバター画像生成 (FluxEngine → FLUX.1-dev + LoRA)
  │     │
  │     ├─→ talking_head: 画像 → Wan2.1 I2V (subprocess) → Wav2Lip リップシンク
  │     │
  │     └─→ cinematic: 画像 + プロンプト → Wan2.1 I2V (subprocess)
  │
  └─→ 合成 (Compositor → FFmpeg): クリップ結合 + BGM + テロップ
```

## cocoro-OS統合情報 (Phase 5用)
- COCORO_CORE_URL: http://192.168.50.92:8001
- API_KEY: cocoro-2026
- agent_type: worker | agent_role: specialist
- schema: v7 | cocoro-net: 172.30.0.0/24

## 移行進捗 (2026-04-21 現在)
- [x] Wan2.1 モデルDL完了 (77GB /data/models/Wan2.1)
- [x] Wav2Lip venv セットアップ完了
- [x] Ollama インストール & Qwen2.5:32b pull 完了
- [x] Style-Bert-VITS2 セットアップ完了 (systemd: style-bert-vits2.service)
- [x] .env 更新 (localhost に切り替え完了)
- [x] E2Eテスト 完了 (台本→音声→Wan2.1→Wav2Lip→合成)
- [x] InstantID ポーズ画像生成 動作確認
- [x] Web UI (ui/index.html) → API 配線修正完了

## 残存バグ・TODO (優先順)
1. **フロントエンド (frontend/) 未着手** - Next.js 15ダッシュボード開発中

## 修正済み
- [x] InstantIDジョブが`pending`のまま - avatars.py のupload_avatarでBGTask前にsession.commit()欠如。修正済み。
- [x] UIのInstantIDポーリングが止まらない - MAX_POLLS=480 (80分) タイムアウトが正常に動作確認済み
- [x] 前回顔写真と今回が別人 - customer_nameパス正規化の不一致が原因。generate_instantid_poses.py/avatars.py内でsafe_name変換をorchestratorの変換と共統。
- [x] output_format=youtubeが不適切 - shortsフォーマットをWan2.1ネイティブ480x832(16fps)に変更。youtube形式に警告コメント追加。
- [x] 単体シーン生成のプレビューURL構築ミス - UIのoutput_path変換をfinishSuccessと共統。
- [x] 進捗(progress)がフルパイプライン中途で止まる - _generate_scene_clip/_generate_cinematic_clip をasyncio.create_subprocess_exec方式に移行。stdout WAN_STEP:/WAN_PHASE: をリアルタイムパースしてon_progressコールバックを呼ぶ。OOMリトライもasyncio.sleepに変更。
