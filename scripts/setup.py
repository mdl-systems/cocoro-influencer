"""
環境セットアップスクリプト

Windows GPU環境にパイプラインの依存関係を一括インストール。
"""

import os
import subprocess
import sys
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()

PYTHON_DEPS = [
    "aiohttp>=3.9",
    "fastapi>=0.109",
    "uvicorn[standard]>=0.27",
    "pydantic>=2.5",
    "moviepy>=1.0.3",
    "Pillow>=10.0",
    "numpy>=1.24",
    "python-dotenv>=1.0",
]

def banner(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}\n")

def run(cmd, cwd=None, check=True):
    print(f"  > {cmd}")
    return subprocess.run(cmd, shell=True, cwd=cwd, check=check)

def check_gpu():
    banner("GPU チェック")
    try:
        r = subprocess.run("nvidia-smi", capture_output=True, text=True)
        if r.returncode == 0:
            for line in r.stdout.split("\n"):
                if "RTX" in line or "CUDA" in line or "Driver" in line:
                    print(f"  {line.strip()}")
            return True
    except FileNotFoundError:
        pass
    print("  ⚠ nvidia-smi が見つかりません。GPUドライバを確認してください。")
    return False

def check_tools():
    banner("必須ツール チェック")
    tools = {"python": "python --version", "git": "git --version", "ffmpeg": "ffmpeg -version"}
    ok = True
    for name, cmd in tools.items():
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            ver = r.stdout.strip().split("\n")[0]
            print(f"  ✅ {name}: {ver}")
        except Exception:
            print(f"  ❌ {name}: 未インストール")
            ok = False
    return ok

def install_python_deps():
    banner("Python依存パッケージ インストール")
    for dep in PYTHON_DEPS:
        run(f"{sys.executable} -m pip install {dep}")

def setup_comfyui():
    banner("ComfyUI セットアップ確認")
    nodes_file = ROOT / "config" / "comfyui_nodes.json"
    if nodes_file.exists():
        with open(nodes_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"  必須ノード数: {len(data.get('required_nodes', []))}")
        print(f"  必須モデル数: {len(data.get('required_models', []))}")
        for n in data.get("required_nodes", []):
            if n.get("priority") == "必須":
                print(f"    📦 {n['name']} ({n.get('phase','?')})")
    else:
        print("  ⚠ comfyui_nodes.json が見つかりません")

def create_dirs():
    banner("ディレクトリ作成")
    for d in ["output", "logs", "tmp", "models"]:
        p = ROOT / d
        p.mkdir(exist_ok=True)
        print(f"  📁 {p}")

def main():
    print("╔══════════════════════════════════════════════════╗")
    print("║  Avatar Video Pipeline - セットアップ             ║")
    print("╚══════════════════════════════════════════════════╝")

    check_gpu()
    if not check_tools():
        print("\n⚠ 必須ツールが不足しています。インストール後に再実行してください。")
    install_python_deps()
    create_dirs()
    setup_comfyui()

    banner("セットアップ完了")
    print("  次のステップ:")
    print("  1. config/.env.example → config/.env にコピーして設定")
    print("  2. ComfyUIをインストール（scripts/install_comfyui.py）")
    print("  3. python main.py --test でテスト実行")

if __name__ == "__main__":
    main()
