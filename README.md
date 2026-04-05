<<<<<<< HEAD
# cocoro-influencer

企業専属AIインフルエンサー生成システム。

実写風リアルアバターが企業を紹介する動画を自動生成します。
RTX 5090 (32GB VRAM) 上で Diffusers/PyTorch を直接実行します。

## セットアップ

```bash
# リポジトリをクローン
git clone https://github.com/mdl-systems/cocoro-influencer.git
cd cocoro-influencer

# 環境構築 (uv)
uv sync

# AIモデルのダウンロード
uv run python scripts/download_models.py
```

## CLI 使用例

```bash
# アバター画像生成
cocoro-inf avatar generate \
    --prompt "ビジネススーツの日本人女性, 30代" \
    --output ./outputs/avatar_001.png \
    --lora ./loras/customer_a.safetensors

# 音声合成
cocoro-inf voice generate \
    --text "こんにちは、株式会社ABCの紹介をします" \
    --output ./outputs/voice_001.wav

# トーキングヘッド生成
cocoro-inf talking-head generate \
    --image ./outputs/avatar_001.png \
    --audio ./outputs/voice_001.wav \
    --output ./outputs/clip_001.mp4

# シネマティック動画生成
cocoro-inf cinematic generate \
    --image ./outputs/avatar_001.png \
    --prompt "オフィスでプレゼンする様子" \
    --output ./outputs/scene_001.mp4

# 動画合成
cocoro-inf compose \
    --clips clip_001.mp4 scene_001.mp4 \
    --bgm ./assets/bgm.mp3 \
    --format youtube \
    --output ./outputs/final.mp4
```

## 技術スタック

| コンポーネント | 技術 |
|---|---|
| AIエンジン | Diffusers / PyTorch |
| 画像生成 | FLUX.2 + LoRA |
| 動画生成 | Wan 2.6 I2V |
| リップシンク | EchoMimic |
| 音声合成 | VOICEVOX |
| CLI | typer |
| 動画合成 | FFmpeg (ffmpeg-python) |
| パッケージ管理 | uv |

## 開発フェーズ

| Phase | 内容 |
|---|---|
| Phase 1 | FluxEngine + LoRA + CLI |
| Phase 2 | WanEngine + EchoMimic + VoiceEngine + Compositor |
| Phase 3 | FastAPI + Next.js + ダッシュボード |
| Phase 4 | LLM台本生成 + ジョブキュー |
| Phase 5 | cocoro-OS統合 |

## テスト

```bash
uv run pytest tests/ -v
```

## ライセンス

Private - MDL Systems
=======
# Avatar Video Pipeline

**3Dアバター × ComfyUI × 動画自動結合** — Windows GPU環境向け統合パイプライン

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-Latest-green)](https://github.com/comfyanonymous/ComfyUI)
[![Blender 4.x](https://img.shields.io/badge/Blender-4.x-orange)](https://www.blender.org/)

## 概要

RTX 4090 / RTX 4500 搭載の Windows GPU レンタルサーバー上で、3Dアバターから実写風AI動画を全自動生成するパイプラインです。

### 主要機能

| 機能 | 説明 |
|------|------|
| **3Dアバター自動レンダリング** | Blenderヘッドレスで VRM モデルからポーズ・表情を連番レンダリング |
| **AI実写化** | FLUX.1 + ControlNet (Canny/Depth) でキャラクター一貫性100%の実写変換 |
| **AI動画生成** | Wan 2.1 I2V で自然な動きの実写動画を生成 |
| **リップシンク** | LivePortrait で音声波形に合わせた精密な口パク |
| **音声合成** | StyleBERT-VITS2 / OpenAI TTS でナレーション自動生成 |
| **自動編集** | MoviePy + FFmpeg でシーン結合・BGM・テロップを自動処理 |

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│                    gpurental.jp Portal                         │
│              (台本入力 → ジョブ作成 → MP4ダウンロード)            │
└──────────────────────┬──────────────────────────────────────────┘
                       │ REST API
┌──────────────────────▼──────────────────────────────────────────┐
│                 APIゲートウェイ (FastAPI)                        │
│              ジョブキュー管理 / 進捗通知 / 認証                    │
└──────┬───────────┬───────────┬───────────┬──────────────────────┘
       │           │           │           │
┌──────▼──┐  ┌─────▼────┐ ┌───▼───┐  ┌───▼────────┐
│ Blender │  │ ComfyUI  │ │  TTS  │  │  Editor    │
│ (3D)    │  │ (AI)     │ │ Engine│  │  (FFmpeg)  │
│         │  │          │ │       │  │            │
│ VRM→PNG │  │ PNG→MP4  │ │ Text  │  │ Scenes→    │
│ Poses   │  │ Wan 2.1  │ │  →WAV │  │ Final MP4  │
│ Depth   │  │ Lip Sync │ │       │  │ + BGM/SRT  │
└─────────┘  └──────────┘ └───────┘  └────────────┘
   GPU: Blender EEVEE     GPU: CUDA     CPU          GPU: NVENC
```

## クイックスタート

### 前提条件

- Windows 10/11 Pro または Windows Server 2022
- NVIDIA RTX 4090 / RTX 4500 (24GB VRAM)
- NVIDIA ドライバ 550+
- Python 3.10+
- Git, FFmpeg

### インストール

```powershell
# 1. リポジトリをクローン
git clone https://github.com/metadatalab/avatar-video-pipeline.git
cd avatar-video-pipeline

# 2. セットアップスクリプトを実行（依存関係の一括インストール）
python scripts/setup.py

# 3. 環境設定
copy config\.env.example config\.env
# .env を編集して必要な設定を入力

# 4. パイプラインテスト（最小構成）
python main.py --test
```

### 最小構成テスト（1枚の3D画像 → 実写動画）

```powershell
# 3D画像から5秒の実写風動画を生成
python main.py --input models/sample_avatar.vrm --duration 5 --output output/test.mp4
```

## プロジェクト構造

```
avatar-video-pipeline/
├── main.py                  # メインオーケストレーター
├── config/
│   ├── .env.example         # 環境変数テンプレート
│   ├── settings.py          # 設定管理
│   └── comfyui_nodes.json   # ComfyUI必須ノードリスト
├── scripts/
│   ├── setup.py             # 環境セットアップ（一括インストール）
│   ├── install_comfyui.py   # ComfyUIインストーラ
│   └── install_models.py    # AIモデルダウンローダ
├── blender/
│   ├── render_avatar.py     # Blenderヘッドレスレンダリング
│   ├── vrm_importer.py      # VRMインポートユーティリティ
│   └── pose_library.json    # プリセットポーズデータ
├── comfyui/
│   ├── client.py            # ComfyUI WebSocket API クライアント
│   ├── workflows/           # ComfyUIワークフロー JSON
│   │   ├── flux_controlnet.json
│   │   ├── wan21_i2v.json
│   │   └── liveportrait_lipsync.json
│   └── node_installer.py    # カスタムノード管理
├── tts/
│   ├── engine.py            # TTS統合エンジン
│   └── style_bert_vits2.py  # StyleBERT-VITS2ラッパー
├── editor/
│   ├── compositor.py        # MoviePy動画結合
│   ├── subtitles.py         # SRTテロップ処理
│   └── effects.py           # トランジション・エフェクト
├── api/
│   ├── server.py            # FastAPIゲートウェイ
│   ├── routes.py            # APIルーティング
│   ├── models.py            # Pydanticスキーマ
│   └── job_queue.py         # ジョブキュー管理
├── models/                  # 3Dモデル・AIモデル格納
├── output/                  # 生成物出力先
├── logs/                    # ログ出力先
├── docs/                    # 開発ドキュメント
└── tests/                   # テストスイート
```

## 開発フェーズ

| Phase | 内容 | 状態 |
|-------|------|------|
| **A** | 基盤環境構築（GPU, Python, ComfyUI） | 🔲 未着手 |
| **B** | 3Dアバター一貫性エンジン（Blender + ControlNet） | 🔲 未着手 |
| **C** | 動画生成パイプライン（Wan 2.1 + LivePortrait） | 🔲 未着手 |
| **D** | 自動結合とデプロイ（FFmpeg + API） | 🔲 未着手 |

## ライセンス

METADATALAB.INC — [gpurental.jp](https://gpurental.jp)
>>>>>>> master
