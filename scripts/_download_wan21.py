"""Wan 2.1 I2V 480P モデルダウンロード"""
from huggingface_hub import snapshot_download
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("Downloading Wan 2.1 I2V 14B-480P (all safetensors + configs)...")
print("This may take 30-60 minutes depending on connection speed...")

try:
    result = snapshot_download(
        "Wan-AI/Wan2.1-I2V-14B-480P",
        local_dir="F:/ComfyUI/models/diffusion_models/Wan2.1-I2V-14B-480P",
        allow_patterns=["*.safetensors", "*.json", "*.txt", "*.model"],
        max_workers=2,  # Limit concurrent downloads
    )
    print(f"Done! Files saved to: {result}")
except Exception as e:
    print(f"Error: {e}")
