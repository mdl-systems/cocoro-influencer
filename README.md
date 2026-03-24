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
