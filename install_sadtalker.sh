#!/bin/bash
# install_sadtalker.sh - SadTalker インストールスクリプト (cocoro-render-01)
# 実行: bash /home/cocoro-influencer/install_sadtalker.sh

set -e

SADTALKER_DIR="/data/models/SadTalker"
VENV_DIR="/data/venv/sadtalker"

echo "=== SadTalker インストール開始 ==="

# ① リポジトリクローン
if [ ! -d "$SADTALKER_DIR" ]; then
    echo "[1/6] SadTalker をクローン中..."
    git clone https://github.com/OpenTalker/SadTalker.git "$SADTALKER_DIR"
else
    echo "[1/6] SadTalker ディレクトリ存在 → git pull"
    cd "$SADTALKER_DIR" && git pull
fi

# ② Python venv 作成
echo "[2/6] Python venv 作成: $VENV_DIR"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip -q

# ③ PyTorch インストール (CUDA 12.6)
echo "[3/6] PyTorch (CUDA 12.6) インストール中..."
"$VENV_DIR/bin/pip" install \
    torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu124 -q

# ④ SadTalker 依存パッケージ
echo "[4/6] SadTalker 依存パッケージインストール中..."
"$VENV_DIR/bin/pip" install \
    face-alignment \
    imageio \
    imageio-ffmpeg \
    scipy \
    numpy \
    pillow \
    pyyaml \
    einops \
    tqdm \
    yacs \
    gdown \
    librosa \
    safetensors \
    resampy \
    av \
    huggingface_hub \
    dlib \
    -q

# ⑤ モデルファイルのダウンロード (HuggingFace)
echo "[5/6] SadTalker モデルをダウンロード中..."
mkdir -p "$SADTALKER_DIR/checkpoints"
mkdir -p "$SADTALKER_DIR/gfpgan/weights"

"$VENV_DIR/bin/python" << 'PYEOF'
from huggingface_hub import hf_hub_download
import os, shutil

dest_checkpoints = "/data/models/SadTalker/checkpoints"
dest_gfpgan      = "/data/models/SadTalker/gfpgan/weights"

# SadTalker 本体チェックポイント
sadtalker_files = [
    "SadTalker_V0.0.2_256.safetensors",
    "SadTalker_V0.0.2_512.safetensors",
    "mapping_00109-model.pth.tar",
    "mapping_00229-model.pth.tar",
]
for f in sadtalker_files:
    dest = f"{dest_checkpoints}/{f}"
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        print(f"  スキップ (既存): {f}")
        continue
    print(f"  ダウンロード中: {f}")
    try:
        path = hf_hub_download(
            repo_id="vinthony/SadTalker",
            filename=f"checkpoints/{f}",
            local_dir="/tmp/sadtalker_dl",
        )
        shutil.copy(path, dest)
        print(f"  完了: {f} ({os.path.getsize(dest)//1024//1024}MB)")
    except Exception as e:
        print(f"  警告: {f} のダウンロード失敗 ({e})")

# GFPGAN 補助モデル
gfpgan_files = [
    ("xinntao/facexlib", "detection_Resnet50_Final.pth", dest_gfpgan),
    ("xinntao/facexlib", "parsing_parsenet.pth",         dest_gfpgan),
]
for repo, fname, dest_dir in gfpgan_files:
    dest = f"{dest_dir}/{fname}"
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        print(f"  スキップ (既存): {fname}")
        continue
    print(f"  ダウンロード中 [{repo}]: {fname}")
    try:
        path = hf_hub_download(repo_id=repo, filename=fname, local_dir="/tmp/sadtalker_gfpgan")
        shutil.copy(path, dest)
        print(f"  完了: {fname}")
    except Exception as e:
        print(f"  警告: {fname} ダウンロード失敗 ({e})")

print("モデルダウンロード完了")
PYEOF

# GFPGAN 本体ウェイト
echo "  GFPGAN GFPGANv1.4.pth ダウンロード..."
GFPGAN_PATH="$SADTALKER_DIR/gfpgan/weights/GFPGANv1.4.pth"
if [ ! -f "$GFPGAN_PATH" ] || [ ! -s "$GFPGAN_PATH" ]; then
    "$VENV_DIR/bin/python" -c "
from huggingface_hub import hf_hub_download
import shutil
path = hf_hub_download(repo_id='Xiaoming010/GFPGAN', filename='GFPGANv1.4.pth', local_dir='/tmp/gfpgan_dl')
shutil.copy(path, '$GFPGAN_PATH')
print('GFPGANv1.4.pth ダウンロード完了')
" || echo "  警告: GFPGANv1.4.pth ダウンロード失敗 (後で手動取得)"
fi

# ⑥ 動作確認
echo "[6/6] インストール確認..."
"$VENV_DIR/bin/python" -c "
import torch
import face_alignment
import librosa
print(f'PyTorch: {torch.__version__}')
print(f'CUDA: {torch.cuda.is_available()} ({torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"})')
print(f'face_alignment: OK')
print(f'librosa: {librosa.__version__}')

# SadTalker のモジュールを確認
import sys
sys.path.insert(0, '/data/models/SadTalker')
from src.utils.preprocess import CropAndExtract
print('SadTalker modules: OK')
"

echo ""
echo "=== SadTalker インストール完了 ==="
echo "  インストール先: $SADTALKER_DIR"
echo "  Python venv:    $VENV_DIR"
echo ""
echo "テスト実行:"
echo "  /data/venv/sadtalker/bin/python /home/cocoro-influencer/scripts/sadtalker_inference.py \\"
echo "    --image /data/outputs/cocoro_customer/avatar.png \\"
echo "    --audio /data/outputs/cocoro_customer/scene_000_voice.wav \\"
echo "    --outfile /tmp/test_sadtalker.mp4"
