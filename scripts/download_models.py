"""download_models.py: AIモデルの一括ダウンロードスクリプト

Phase 1-2で使用するすべてのAIモデルをダウンロードする。
初回セットアップ時に1回だけ実行する。
"""

import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# モデル保存先ディレクトリ
MODELS_DIR = Path(__file__).parent.parent / "models"


def download_flux() -> None:
    """FLUX.1-dev モデルをダウンロードする"""
    from diffusers import FluxPipeline

    model_id = "black-forest-labs/FLUX.1-dev"
    save_path = MODELS_DIR / "flux1-dev"

    if save_path.exists():
        logger.info("FLUX.1-dev: 既にダウンロード済みです (%s)", save_path)
        return

    logger.info("FLUX.1-dev: ダウンロード開始... (数分かかります)")
    pipe = FluxPipeline.from_pretrained(model_id)
    pipe.save_pretrained(str(save_path))
    logger.info("FLUX.1-dev: ダウンロード完了 (%s)", save_path)


def download_wan() -> None:
    """Wan 2.1 I2V モデルをダウンロードする"""
    from diffusers import WanImageToVideoPipeline

    model_id = "Wan-AI/Wan2.1-I2V-14B-720P-Diffusers"
    save_path = MODELS_DIR / "wan2.1-i2v"

    if save_path.exists():
        logger.info("Wan 2.1 I2V: 既にダウンロード済みです (%s)", save_path)
        return

    logger.info("Wan 2.1 I2V: ダウンロード開始... (大容量です。時間がかかります)")
    pipe = WanImageToVideoPipeline.from_pretrained(model_id)
    pipe.save_pretrained(str(save_path))
    logger.info("Wan 2.1 I2V: ダウンロード完了 (%s)", save_path)


def download_echomimic() -> None:
    """EchoMimic モデルをダウンロードする"""
    import subprocess

    echo_dir = MODELS_DIR / "echomimic"

    if echo_dir.exists():
        logger.info("EchoMimic: 既にダウンロード済みです (%s)", echo_dir)
        return

    logger.info("EchoMimic: リポジトリをクローン中...")
    result = subprocess.run(
        ["git", "clone", "https://github.com/BadToBest/EchoMimic.git", str(echo_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logger.error("EchoMimic: クローン失敗\n%s", result.stderr)
        return

    # EchoMimicのモデルウェイトをダウンロード
    logger.info("EchoMimic: モデルウェイトをダウンロード中...")
    weights_script = echo_dir / "download_weights.sh"
    if weights_script.exists():
        subprocess.run(["bash", str(weights_script)], cwd=str(echo_dir), check=False)

    logger.info("EchoMimic: ダウンロード完了 (%s)", echo_dir)


def check_voicevox() -> None:
    """VOICEVOXのインストール状態を確認する"""
    import socket

    logger.info("VOICEVOX ENGINE: 接続確認中 (http://localhost:50021)...")
    try:
        sock = socket.create_connection(("localhost", 50021), timeout=3)
        sock.close()
        logger.info("VOICEVOX ENGINE: 接続OK")
    except (ConnectionRefusedError, TimeoutError, OSError):
        logger.warning(
            "VOICEVOX ENGINE: 接続できません。\n"
            "  以下のいずれかの方法で起動してください:\n"
            "  1. https://voicevox.hiroshiba.jp/ からダウンロード\n"
            "  2. Docker: docker run -p 50021:50021 voicevox/voicevox_engine"
        )


def main() -> None:
    """全モデルをダウンロードする"""
    MODELS_DIR.mkdir(exist_ok=True)

    logger.info("=" * 50)
    logger.info("cocoro-influencer モデルダウンロード開始")
    logger.info("保存先: %s", MODELS_DIR.resolve())
    logger.info("=" * 50)

    # コマンドライン引数でモデルを選択可能
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["all"]

    if "all" in targets or "flux" in targets:
        download_flux()

    if "all" in targets or "wan" in targets:
        download_wan()

    if "all" in targets or "echomimic" in targets:
        download_echomimic()

    if "all" in targets or "voicevox" in targets:
        check_voicevox()

    logger.info("=" * 50)
    logger.info("ダウンロード完了")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
