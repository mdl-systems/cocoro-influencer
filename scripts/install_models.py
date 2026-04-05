"""
AIモデル ダウンロードスクリプト

comfyui_nodes.json に定義されたモデルを HuggingFace から
ComfyUIのモデルディレクトリに自動ダウンロードする。

使用方法:
  python scripts/install_models.py --comfyui-path C:\ComfyUI
  python scripts/install_models.py --list          # モデル一覧のみ表示
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()

# モデル配置マッピング: type → ComfyUI内のサブディレクトリ
MODEL_DIR_MAP = {
    "checkpoint": "models/checkpoints",
    "video_model": "models/checkpoints",
    "controlnet": "models/controlnet",
    "liveportrait": "models/liveportrait",
    "lora": "models/loras",
    "vae": "models/vae",
    "clip": "models/clip",
    "unet": "models/unet",
}


def banner(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}\n")


def load_model_list():
    nodes_file = ROOT / "config" / "comfyui_nodes.json"
    with open(nodes_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("required_models", [])


def check_huggingface_cli():
    """huggingface-cli の存在確認"""
    try:
        r = subprocess.run("huggingface-cli --version", shell=True,
                          capture_output=True, text=True)
        if r.returncode == 0:
            return True
    except Exception:
        pass
    print("  ⚠ huggingface-cli が見つかりません")
    print("  📦 インストール中: pip install huggingface_hub[cli]")
    subprocess.run(f"{sys.executable} -m pip install huggingface_hub[cli]",
                  shell=True, check=True)
    return True


def download_model_hf(repo_url: str, target_dir: Path, model_type: str):
    """HuggingFace からモデルをダウンロード"""
    # URLからrepo_idを抽出 (https://huggingface.co/owner/repo → owner/repo)
    repo_id = repo_url.replace("https://huggingface.co/", "").strip("/")

    target_dir.mkdir(parents=True, exist_ok=True)

    cmd = (
        f'huggingface-cli download {repo_id} '
        f'--local-dir "{target_dir / repo_id.split("/")[-1]}" '
        f'--local-dir-use-symlinks False'
    )
    print(f"  > {cmd}")
    result = subprocess.run(cmd, shell=True, check=False,
                           capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ❌ ダウンロード失敗: {result.stderr[:200]}")
        return False

    print(f"  ✅ ダウンロード完了: {repo_id}")
    return True


def list_models():
    """モデル一覧を表示"""
    models = load_model_list()
    total_gb = 0
    print(f"\n  {'#':>2}  {'名前':<30} {'サイズ':>8}  {'VRAM':>6}  タイプ")
    print(f"  {'─'*2}  {'─'*30} {'─'*8}  {'─'*6}  {'─'*12}")
    for i, m in enumerate(models, 1):
        size = m.get("size_gb", 0)
        total_gb += size
        print(f"  {i:>2}  {m['name']:<30} {size:>6.1f}GB  {m.get('vram_min_gb',0):>4}GB  {m['type']}")
    print(f"\n  合計: {total_gb:.1f}GB (ダウンロード容量)")
    return models


def main():
    parser = argparse.ArgumentParser(description="AI Model Downloader")
    parser.add_argument("--comfyui-path", type=str, default=r"C:\ComfyUI",
                       help="ComfyUI インストールパス")
    parser.add_argument("--list", action="store_true",
                       help="モデル一覧のみ表示")
    parser.add_argument("--model", type=str, default=None,
                       help="特定モデルのみダウンロード (名前)")
    args = parser.parse_args()

    print("╔══════════════════════════════════════════════════╗")
    print("║  AI Model Downloader                            ║")
    print("║  Avatar Video Pipeline                          ║")
    print("╚══════════════════════════════════════════════════╝")

    models = load_model_list()

    if args.list:
        list_models()
        return

    comfyui_path = Path(args.comfyui_path).resolve()
    if not comfyui_path.exists():
        print(f"  ❌ ComfyUIが見つかりません: {comfyui_path}")
        print(f"     先に install_comfyui.py を実行してください")
        sys.exit(1)

    banner("モデル一覧")
    list_models()

    banner("ダウンロード開始")
    check_huggingface_cli()

    # フィルタ
    if args.model:
        models = [m for m in models if args.model.lower() in m["name"].lower()]
        if not models:
            print(f"  ❌ '{args.model}' に一致するモデルが見つかりません")
            sys.exit(1)

    success = 0
    fail = 0

    for i, model in enumerate(models, 1):
        name = model["name"]
        url = model["url"]
        model_type = model["type"]
        size_gb = model.get("size_gb", 0)

        sub_dir = MODEL_DIR_MAP.get(model_type, "models/checkpoints")
        target = comfyui_path / sub_dir

        print(f"\n  [{i}/{len(models)}] {name} ({size_gb:.1f}GB)")
        print(f"  → {target}")

        if download_model_hf(url, target, model_type):
            success += 1
        else:
            fail += 1

    banner("ダウンロード結果")
    print(f"  ✅ 成功: {success}")
    if fail > 0:
        print(f"  ❌ 失敗: {fail}")
    print(f"\n  次のステップ:")
    print(f"    1. ComfyUI を起動: start_comfyui.bat")
    print(f"    2. パイプラインテスト: python main.py --test")


if __name__ == "__main__":
    main()
