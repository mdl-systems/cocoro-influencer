# Cocoro Influencer - Hybrid Avatar Pipeline

**企業専属AIインフルエンサー生成システム (ハイブリッド版)**
実写風リアルアバターが企業を紹介する動画を自動生成します。

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-green)](https://fastapi.tiangolo.com/)

## 🚀 オリジナル（デフォルト）シナリオからの主な変更点・進化

もともとの `cocoro-influencer` は、「RTX 5090 (32GB VRAM) 上で Diffusers/PyTorch を直接（フルローカル）実行する」という極めて要求スペックの高いシナリオでした。
今回のプロジェクトでは、チーム開発と実運用時の安定性を最優先し、以下のように**「ハイブリッド・モジュール・アーキテクチャ」**へと大きく進化させています。

1. **APIハイブリッド処理によるマシンスペック依存の脱却**
   * （変更前）全ての画像生成・リップシンク・シネマティック映像生成をローカルのGPU（ComfyUI / PyTorch等）で実行。（環境構築が難しく、VRAM不足でのフリーズが多発）
   * （現在）もっともGPU負荷の高い「高品質映像生成（Kling I2V）」や「精密なリップシンク（Sync.so）」を商用APIへオフロード。これにより、ローカルPCがフリーズすることなく、世界最高峰の映像品質を安定して出力可能になりました。
2. **Web UI の統合**
   * （変更前）CUI（コマンドライン）からの実行のみ。
   * （現在）チームの誰でもブラウザから直感的にアバター画像の選択や台本入力を実施できるWebフロントエンド（`ui/`）およびFastAPIサーバーを統合。
3. **完全なモジュール分割（1リポジトリ・チーム並行開発）**
   * （変更前）全体が密結合した1つのPythonスクリプト。
   * （現在）`src/modules/` 配下で、台本生成、画像生成、リップシンクなどを完全に別々のディレクトリに独立。LLM担当者と動画担当者が同時に開発を進められます。

---

## 🏗 新生アーキテクチャ図（ローカル実行）

※ 本プロジェクトは外部のGPUポータル（gpurental.jp等）には依存せず、完全に独立したシステムとして動作します。

```text
┌────────────────────────────────────────────────────────────┐
│                       Web UI (Browser)                     │
│    (台本入力 / アバター選択 / シーン設定 / プレビュー確認)    │
└────────────────────────────┬───────────────────────────────┘
                             │ REST API
┌────────────────────────────▼───────────────────────────────┐
│                    API Gateway (FastAPI)                   │
│                        (src/api/)                          │
└────────┬───────────────────┬──────────────────────┬────────┘
         │                   │                      │
┌────────▼───────┐  ┌────────▼───────┐  ┌───────────▼────────┐
│  AI Script Gen │  │ Voice Gen (TTS)│  │ Video & LipSync    │
│  (src/modules) │  │ (src/modules)  │  │ (src/modules)      │
│                │  │                │  │                    │
│ Ollama 120B 等 │  │ StyleBERT-VITS2│  │ Kling AI (I2V API) │
│ (LLM Local/API)│  │ (Local TTS)    │  │ Sync.so (LipSync)  │
└────────┬───────┘  └────────┬───────┘  └───────────┬────────┘
         │                   │                      │
┌────────▼───────────────────▼──────────────────────▼────────┐
│                    Compositor (FFmpeg)                     │
│              (全シーン結合・テロップ焼き付け・BGM付与)             │
│                      (src/modules)                         │
└────────────────────────────┬───────────────────────────────┘
                             │
                      [ Output MP4 ]
```

## 📂 プロジェクト構造

チームで並行開発が可能なモジュール構造です。（詳細は `docs/DESIGN_SPEC.md` を参照）

```text
hybrid-avatar-pipeline/
├── docs/
│   └── DESIGN_SPEC.md           # 開発仕様書・モジュール入出力定義
├── src/
│   ├── modules/
│   │   ├── analyzer/            # URL解析・参考動画分析
│   │   ├── script_gen/          # AI台本自動生成
│   │   ├── avatar_gen/          # キャラ固定・ベース画像生成
│   │   ├── voice_gen/           # 音声合成・声生成
│   │   ├── video_gen/           # 動画作成 (Kling API)
│   │   ├── lipsync/             # リップシンク (SyncLabs API)
│   │   └── compositor/          # 最終レンダリング・映像結合
│   ├── api/                     # FastAPI サーバー
│   └── cli.py                   # コマンドラインツール
├── ui/                          # WebUI (HTML/CSS/JS)
├── config/                      # 環境変数 (.env)
├── assets/                      # BGM、フォント等
└── requirements.txt
```

## 🛠 クイックスタート (新PCへの移行)

```powershell
# 1. リポジトリをクローン（またはZip展開）
git clone -b master https://github.com/mdl-systems/cocoro-influencer.git
cd cocoro-influencer

# 2. 仮想環境の作成と依存関係のインストール
python -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt

# 3. .env の配置
# config/.env ファイルを作成し、各種APIキー（Kling, SyncLabs等）を設定

# 4. Web UI サーバーの起動
run_hybrid_ui.bat
```
ブラウザで `http://localhost:8082` にアクセスしてください。
