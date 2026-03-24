"""EchoMimicEngine: EchoMimic によるリップシンクトーキングヘッド生成エンジン

アバター画像 + 音声WAVを入力として、
口元が音声に合わせて動くトーキングヘッド動画を生成する。
"""

import logging
import subprocess
from pathlib import Path

from src.engines.base import BaseEngine

logger = logging.getLogger(__name__)

# EchoMimicのデフォルトリポジトリパス
DEFAULT_ECHOMIMIC_PATH = Path("models/echomimic")


class EchoMimicEngine(BaseEngine):
    """EchoMimic によるリップシンクトーキングヘッド生成エンジン

    画像 + 音声 → リップシンク動画 (MP4) を生成する。
    EchoMimicはサブプロセスとして呼び出す。
    """

    def __init__(
        self,
        echomimic_path: Path = DEFAULT_ECHOMIMIC_PATH,
    ) -> None:
        """EchoMimicEngineの初期化

        Args:
            echomimic_path: EchoMimicモデルのディレクトリパス
        """
        super().__init__()
        self._echomimic_path: Path = echomimic_path
        self._model_loaded: bool = False

    def load(self) -> None:
        """EchoMimicモデルの準備確認

        EchoMimicはサブプロセス実行のため、モデルファイルの
        存在確認のみ行う。
        """
        logger.info("EchoMimicEngine: モデルパス確認 (%s)", self._echomimic_path)
        # モデルディレクトリの存在確認
        if not self._echomimic_path.exists():
            logger.warning(
                "EchoMimicEngine: モデルディレクトリが見つかりません: %s "
                "(download_models.pyでダウンロードしてください)",
                self._echomimic_path,
            )
        self._is_loaded = True
        logger.info("EchoMimicEngine: ロード完了")

    def unload(self) -> None:
        """EchoMimicEngineのアンロード"""
        super().unload()
        logger.info("EchoMimicEngine: アンロード完了")

    def generate(
        self,
        *,
        image_path: Path,
        audio_path: Path,
        output_path: Path,
        width: int = 512,
        height: int = 512,
        num_inference_steps: int = 20,
        seed: int | None = None,
    ) -> Path:
        """リップシンクトーキングヘッド動画を生成する

        Args:
            image_path: 入力アバター画像パス
            audio_path: 入力音声WAVファイルパス
            output_path: 出力MP4ファイルパス
            width: 出力動画幅 (ピクセル)
            height: 出力動画高さ (ピクセル)
            num_inference_steps: 推論ステップ数
            seed: ランダムシード

        Returns:
            生成した動画ファイルのパス

        Raises:
            RuntimeError: モデルが未ロードの場合
            FileNotFoundError: 入力ファイルが存在しない場合
        """
        if not self._is_loaded:
            raise RuntimeError("EchoMimicEngine: ロードされていません。先にload()を呼んでください")

        if not image_path.exists():
            raise FileNotFoundError(f"入力画像が見つかりません: {image_path}")

        if not audio_path.exists():
            raise FileNotFoundError(f"入力音声が見つかりません: {audio_path}")

        # 出力ディレクトリ作成
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "EchoMimicEngine: トーキングヘッド生成開始 (image=%s, audio=%s)",
            image_path,
            audio_path,
        )

        # EchoMimicをサブプロセスで実行
        cmd = [
            "python",
            str(self._echomimic_path / "inference.py"),
            "--image_path", str(image_path.resolve()),
            "--audio_path", str(audio_path.resolve()),
            "--output_path", str(output_path.resolve()),
            "--width", str(width),
            "--height", str(height),
            "--num_inference_steps", str(num_inference_steps),
        ]
        if seed is not None:
            cmd += ["--seed", str(seed)]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"EchoMimic実行エラー (returncode={result.returncode}):\n{result.stderr}"
            )

        logger.info("EchoMimicEngine: 動画生成完了 (%s)", output_path)
        return output_path
