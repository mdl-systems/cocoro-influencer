"""
ComfyUI 自動インストールスクリプト

Windows GPU環境にComfyUIポータブル版をインストールし、
必須カスタムノードを一括セットアップする。

使用方法:
  python scripts/install_comfyui.py [--path C:\ComfyUI] [--skip-nodes]
"""

import argparse
import json
import os
import subprocess
import sys
import zipfile
import urllib.request
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()

# ComfyUI ポータブル版 (Windows)
COMFYUI_PORTABLE_URL = "https://github.com/comfyanonymous/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z"
COMFYUI_GIT_URL = "https://github.com/comfyanonymous/ComfyUI.git"


def banner(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}\n")


def run(cmd, cwd=None, check=True):
    print(f"  > {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, check=check,
                           capture_output=True, text=True)
    if result.stdout.strip():
        for line in result.stdout.strip().split("\n")[:5]:
            print(f"    {line}")
    if result.returncode != 0 and result.stderr:
        print(f"  ⚠ {result.stderr[:200]}")
    return result


def check_prerequisites():
    """前提条件チェック"""
    banner("前提条件チェック")

    # Python バージョン
    ver = sys.version_info
    if ver.major < 3 or ver.minor < 10:
        print(f"  ❌ Python 3.10+ が必要です (現在: {sys.version})")
        return False
    print(f"  ✅ Python {sys.version}")

    # Git
    try:
        run("git --version", check=True)
        print("  ✅ Git")
    except Exception:
        print("  ❌ Git が見つかりません")
        return False

    # CUDA
    try:
        r = run("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader", check=True)
        gpu_info = r.stdout.strip()
        print(f"  ✅ GPU: {gpu_info}")
    except Exception:
        print("  ⚠ nvidia-smi が見つかりません（GPUなし環境？）")

    return True


def install_comfyui_git(install_path: Path):
    """ComfyUIをGitクローンでインストール"""
    banner(f"ComfyUI インストール → {install_path}")

    if (install_path / "main.py").exists():
        print("  ⏭ ComfyUI は既にインストール済みです")
        # 最新に更新
        print("  🔄 最新版に更新中...")
        run("git pull", cwd=str(install_path), check=False)
        return

    install_path.mkdir(parents=True, exist_ok=True)
    run(f"git clone {COMFYUI_GIT_URL} .", cwd=str(install_path))

    # venv 作成
    banner("Python仮想環境 (venv) セットアップ")
    venv_path = install_path / "venv"
    if not venv_path.exists():
        run(f"{sys.executable} -m venv {venv_path}")

    pip = str(venv_path / "Scripts" / "pip.exe")

    # PyTorch (CUDA 12.x)
    print("  📦 PyTorch + CUDA インストール中...")
    run(f'"{pip}" install torch torchvision torchaudio '
        f'--index-url https://download.pytorch.org/whl/cu124')

    # ComfyUI依存パッケージ
    req_file = install_path / "requirements.txt"
    if req_file.exists():
        run(f'"{pip}" install -r "{req_file}"')

    # xformers (推奨: VRAM効率化)
    print("  📦 xformers インストール中...")
    run(f'"{pip}" install xformers', check=False)

    print("  ✅ ComfyUI インストール完了")


def install_custom_nodes(install_path: Path, skip: bool = False):
    """カスタムノードを一括インストール"""
    if skip:
        print("  ⏭ カスタムノードのインストールをスキップ")
        return

    banner("カスタムノード インストール")

    nodes_file = ROOT / "config" / "comfyui_nodes.json"
    if not nodes_file.exists():
        print(f"  ❌ {nodes_file} が見つかりません")
        return

    with open(nodes_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    custom_nodes_dir = install_path / "custom_nodes"
    custom_nodes_dir.mkdir(exist_ok=True)

    nodes = data.get("required_nodes", [])
    total = len(nodes)

    for i, node in enumerate(nodes, 1):
        name = node["name"]
        repo = node["repo"]
        priority = node.get("priority", "オプション")
        phase = node.get("phase", "?")

        node_dir = custom_nodes_dir / name
        status = "🔄 更新" if node_dir.exists() else "📦 インストール"

        print(f"\n  [{i}/{total}] {status} {name} (Phase {phase}, {priority})")
        print(f"         {repo}")

        if node_dir.exists():
            # 既存ノードの更新
            run("git pull", cwd=str(node_dir), check=False)
        else:
            # 新規クローン
            r = run(f"git clone {repo} {name}", cwd=str(custom_nodes_dir), check=False)
            if r.returncode != 0:
                print(f"  ❌ {name} のクローンに失敗しました")
                continue

        # ノード固有の依存パッケージ
        node_req = node_dir / "requirements.txt"
        if node_req.exists():
            pip = str(install_path / "venv" / "Scripts" / "pip.exe")
            if Path(pip).exists():
                run(f'"{pip}" install -r "{node_req}"', check=False)

    print(f"\n  ✅ {total} 個のカスタムノード処理完了")


def create_start_script(install_path: Path):
    """ComfyUI起動バッチファイルを生成"""
    banner("起動スクリプト生成")

    bat_content = f'''@echo off
title ComfyUI - Avatar Video Pipeline
echo ==========================================
echo   ComfyUI Starting (Avatar Video Pipeline)
echo ==========================================
echo.

cd /d "{install_path}"

REM venv環境がある場合はアクティベート
if exist "venv\\Scripts\\activate.bat" (
    call venv\\Scripts\\activate.bat
)

REM GPU メモリ最適化
set PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

REM ComfyUI起動 (APIモード有効, ポート8188)
python main.py ^
    --listen 0.0.0.0 ^
    --port 8188 ^
    --enable-cors-header "*" ^
    --preview-method auto ^
    --use-pytorch-cross-attention

echo.
echo ComfyUI has stopped.
pause
'''

    bat_path = ROOT / "start_comfyui.bat"
    with open(bat_path, "w", encoding="shift-jis") as f:
        f.write(bat_content)
    print(f"  ✅ {bat_path}")

    # xformers 版の起動スクリプト
    bat_xformers = bat_content.replace(
        "--use-pytorch-cross-attention",
        "--use-split-cross-attention"
    )
    bat_xformers_path = ROOT / "start_comfyui_xformers.bat"
    with open(bat_xformers_path, "w", encoding="shift-jis") as f:
        f.write(bat_xformers)
    print(f"  ✅ {bat_xformers_path}")


def create_service_setup(install_path: Path):
    """Windowsタスクスケジューラ登録スクリプトを生成"""
    ps_content = f'''# ComfyUI を Windows タスクスケジューラに登録
# 管理者権限で実行してください

$taskName = "ComfyUI-AvatarPipeline"
$batPath = "{ROOT}\\start_comfyui.bat"

# 既存タスクを削除
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# トリガー: ログオン時に自動起動
$trigger = New-ScheduledTaskTrigger -AtLogOn

# アクション
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$batPath`""

# 設定
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# 登録
Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action -Settings $settings -RunLevel Highest

Write-Host "✅ タスク '$taskName' を登録しました"
Write-Host "   ログオン時に ComfyUI が自動起動します"
'''

    ps_path = ROOT / "scripts" / "register_task.ps1"
    with open(ps_path, "w", encoding="utf-8") as f:
        f.write(ps_content)
    print(f"  ✅ タスクスケジューラ登録スクリプト: {ps_path}")


def main():
    parser = argparse.ArgumentParser(description="ComfyUI Installer")
    parser.add_argument("--path", type=str, default=r"C:\ComfyUI",
                       help="ComfyUI インストール先 (default: C:\\ComfyUI)")
    parser.add_argument("--skip-nodes", action="store_true",
                       help="カスタムノードのインストールをスキップ")
    args = parser.parse_args()

    install_path = Path(args.path).resolve()

    print("╔══════════════════════════════════════════════════╗")
    print("║  ComfyUI インストーラー                           ║")
    print("║  Avatar Video Pipeline                           ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"  インストール先: {install_path}")

    if not check_prerequisites():
        print("\n❌ 前提条件を満たしていません。修正後に再実行してください。")
        sys.exit(1)

    install_comfyui_git(install_path)
    install_custom_nodes(install_path, skip=args.skip_nodes)
    create_start_script(install_path)
    create_service_setup(install_path)

    banner("インストール完了")
    print("  次のステップ:")
    print(f"  1. AIモデルをダウンロード: python scripts/install_models.py --comfyui-path {install_path}")
    print(f"  2. ComfyUI を起動: start_comfyui.bat")
    print(f"  3. パイプラインテスト: python main.py --test")


if __name__ == "__main__":
    main()
