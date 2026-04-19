"""WanEngine: Wan 2.6 I2V によるシネマティック動画生成エンジン

画像 + テキストプロンプトを入力として、
シネマティックな動画クリップを生成する。
"""

import logging
from pathlib import Path

from src.engines.base import BaseEngine

logger = logging.getLogger(__name__)

# デフォルトモデルID
DEFAULT_MODEL_ID = "Wan-AI/Wan2.1-I2V-14B-720P-Diffusers"
# ※ torch は load() 内で遅延インポートする（main venvにtorchがない環境対応）


class WanEngine(BaseEngine):
    """Wan 2.6 I2V によるシネマティック動画生成エンジン

    画像とプロンプトからシネマティックな動画を生成する。
    RTX 5090 (32GB VRAM) で float16 推論を行う。
    """

    def __init__(self, model_id: str = DEFAULT_MODEL_ID) -> None:
        """WanEngineの初期化

        Args:
            model_id: HuggingFaceモデルID
        """
        super().__init__()
        self._model_id: str = model_id
        self._pipe: object | None = None

    def load(self) -> None:
        """Wan 2.6 I2Vモデルをロードする"""
        import torch  # 遅延インポート（main venvにtorchがなくても起動できるように）
        from diffusers import WanImageToVideoPipeline

        logger.info("WanEngine: モデルロード開始 (%s)", self._model_id)
        self._pipe = WanImageToVideoPipeline.from_pretrained(
            self._model_id,
            torch_dtype=torch.float16,
        )
        self._pipe.to("cuda")
        self._is_loaded = True
        logger.info("WanEngine: モデルロード完了")

    def unload(self) -> None:
        """モデルをアンロードしてGPUメモリを解放する"""
        self._pipe = None
        super().unload()
        logger.info("WanEngine: アンロード完了")

    def generate(
        self,
        *,
        image_path: Path,
        prompt: str,
        output_path: Path,
        negative_prompt: str = "blurry, low quality, watermark",
        num_frames: int = 81,
        num_inference_steps: int = 50,
        guidance_scale: float = 5.0,
        seed: int | None = None,
    ) -> Path:
        """シネマティック動画を生成する

        Args:
            image_path: 入力画像ファイルパス
            prompt: 動画生成プロンプト
            output_path: 出力MP4ファイルパス
            negative_prompt: ネガティブプロンプト
            num_frames: 生成フレーム数 (デフォルト: 81 = 約3秒@24fps)
            num_inference_steps: 推論ステップ数
            guidance_scale: ガイダンススケール
            seed: ランダムシード

        Returns:
            生成した動画ファイルのパス

        Raises:
            RuntimeError: モデルが未ロードの場合
            FileNotFoundError: 入力画像が存在しない場合
        """
        if self._pipe is None:
            raise RuntimeError("WanEngine: モデルが未ロードです。先にload()を呼んでください")

        if not image_path.exists():
            raise FileNotFoundError(f"入力画像が見つかりません: {image_path}")

        from PIL import Image

        # シード固定（Generatorもtorchを使用するため遅延インポート）
        import torch  # noqa: PLC0415
        generator: torch.Generator | None = None
        if seed is not None:
            generator = torch.Generator(device="cuda").manual_seed(seed)
            logger.info("WanEngine: シード固定 (%d)", seed)

        # 出力ディレクトリ作成
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 入力画像読み込み
        image = Image.open(image_path).convert("RGB")

        logger.info(
            "WanEngine: 動画生成開始 (frames=%d, steps=%d, prompt='%s')",
            num_frames,
            num_inference_steps,
            prompt[:50],
        )

        result = self._pipe(
            image=image,
            prompt=prompt,
            negative_prompt=negative_prompt,
            num_frames=num_frames,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            generator=generator,
        )

        # 動画フレームをMP4として保存
        frames = result.frames[0]
        self._save_frames_as_video(frames, output_path)

        logger.info("WanEngine: 動画保存完了 (%s)", output_path)
        return output_path

    def _save_frames_as_video(
        self,
        frames: list,
        output_path: Path,
        fps: int = 24,
    ) -> None:
        """フレームリストをMP4ファイルとして保存する

        Args:
            frames: PIL Imageフレームのリスト
            output_path: 出力MP4ファイルパス
            fps: フレームレート
        """
        import ffmpeg

        # 一時フレームディレクトリ
        frame_dir = output_path.parent / f".tmp_{output_path.stem}_frames"
        frame_dir.mkdir(parents=True, exist_ok=True)

        try:
            # フレームをPNGとして保存
            for i, frame in enumerate(frames):
                frame.save(frame_dir / f"frame_{i:05d}.png")

            # FFmpegでMP4に変換
            (
                ffmpeg
                .input(str(frame_dir / "frame_%05d.png"), framerate=fps)
                .output(
                    str(output_path),
                    vcodec="libx264",
                    pix_fmt="yuv420p",
                    crf=18,
                )
                .overwrite_output()
                .run(quiet=True)
            )
        finally:
            # 一時ファイルを削除
            import shutil
            shutil.rmtree(frame_dir, ignore_errors=True)
