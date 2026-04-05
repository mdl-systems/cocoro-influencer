"""
全AIモデル一括ダウンロード (認証不要版)

1ファイルずつ順番にダウンロードし、レート制限を回避。
"""
import sys
import time
sys.stdout.reconfigure(encoding='utf-8')

from huggingface_hub import hf_hub_download, snapshot_download
from pathlib import Path

COMFYUI = "F:/ComfyUI"

def dl(repo, filename, subdir, desc=""):
    target = Path(COMFYUI) / subdir
    target.mkdir(parents=True, exist_ok=True)
    print(f"\n{'='*50}")
    print(f"  {desc or filename}")
    print(f"  {repo} / {filename}")
    print(f"  -> {target}")
    print(f"{'='*50}")
    try:
        result = hf_hub_download(
            repo_id=repo,
            filename=filename,
            local_dir=str(target / repo.split('/')[-1]),
            local_dir_use_symlinks=False,
        )
        print(f"  OK: {result}")
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False

print("=" * 60)
print("  Avatar Video Pipeline - Model Downloader")
print("  認証不要モデルを順番にダウンロード")
print("=" * 60)

success = 0
fail = 0

# === Wan 2.1 I2V 14B 480P (7 parts) ===
wan_repo = "Wan-AI/Wan2.1-I2V-14B-480P"
wan_dir = "models/diffusion_models"

for i in range(1, 8):
    fname = f"diffusion_pytorch_model-{i:05d}-of-00007.safetensors"
    ok = dl(wan_repo, fname, wan_dir, f"Wan 2.1 I2V Part {i}/7")
    if ok:
        success += 1
    else:
        fail += 1
    time.sleep(2)  # レート制限回避

# Wan 2.1 config files
for cfg in ["diffusion_pytorch_model.safetensors.index.json", "config.json"]:
    dl(wan_repo, cfg, wan_dir, f"Wan 2.1 {cfg}")

# Wan 2.1 text encoders
for te_file in [
    "google/umt5-xxl/config.json",
    "google/umt5-xxl/tokenizer.json",
    "google/umt5-xxl/tokenizer_config.json",
    "google/umt5-xxl/special_tokens_map.json",
    "xlm-roberta-large/config.json",
    "xlm-roberta-large/tokenizer.json",
    "xlm-roberta-large/tokenizer_config.json",
    "xlm-roberta-large/special_tokens_map.json",
]:
    dl(wan_repo, te_file, wan_dir, f"Wan 2.1 text encoder: {te_file}")

# Wan 2.1 CLIP model
for clip_f in [
    "models_clip/open_clip_vit_h_14.pth",
]:
    try:
        dl(wan_repo, clip_f, wan_dir, "Wan 2.1 CLIP")
    except:
        pass

print(f"\n{'='*60}")
print(f"  Result: {success} OK, {fail} FAILED")
print(f"{'='*60}")
