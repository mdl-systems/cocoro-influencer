"""FluxEngine: FLUX.2 + LoRA によるアバター画像生成エンジン

Diffusersライブラリを使用してFLUX.2モデルを直接呼び出し、
企業専属AIインフルエンサーのアバター画像を生成する。
"""

import logging
from pathlib import Path

import torch

from src.engines.base import BaseEngine

logger = logging.getLogger(__name__)

# デフォルトモデルID
DEFAULT_MODEL_ID = "/home/cocoro-influencer/models/flux"


class FluxEngine(BaseEngine):
    """FLUX.2 + LoRA によるアバター画像生成エンジン

    RTX 5090 (32GB VRAM) で float16 推論を行う。
    LoRAを適用して顧客固有のアバターを一貫生成できる。
    """

    def __init__(self, model_id: str = DEFAULT_MODEL_ID) -> None:
        """FluxEngineの初期化

        Args:
            model_id: HuggingFaceモデルID
        """
        super().__init__()
        self._model_id: str = model_id
        self._pipe: object | None = None
        self._current_lora: Path | None = None

    def load(self) -> None:
        """FLUX.2モデルをGPUにロードする"""
        from diffusers import FluxPipeline

        logger.info("FluxEngine: モデルロード開始 (%s)", self._model_id)
        self._pipe = FluxPipeline.from_pretrained(
            self._model_id,
            torch_dtype=torch.bfloat16,
            local_files_only=True,
        )
        self._pipe.enable_model_cpu_offload()
        self._pipe.enable_sequential_cpu_offload()
        self._is_loaded = True
        logger.info("FluxEngine: モデルロード完了")

    def unload(self) -> None:
        """モデルをアンロードしてGPUメモリを解放する"""
        self._pipe = None
        self._current_lora = None
        super().unload()
        logger.info("FluxEngine: アンロード完了")

    def load_lora(self, lora_path: Path) -> None:
        """LoRAウェイトをロードする

        Args:
            lora_path: LoRA safetensorsファイルのパス

        Raises:
            RuntimeError: パイプラインが未ロードの場合
            FileNotFoundError: LoRAファイルが存在しない場合
        """
        if self._pipe is None:
            raise RuntimeError("FluxEngine: モデルが未ロードです。先にload()を呼んでください")

        if not lora_path.exists():
            raise FileNotFoundError(f"LoRAファイルが見つかりません: {lora_path}")

        logger.info("FluxEngine: LoRAロード (%s)", lora_path)
        self._pipe.load_lora_weights(str(lora_path.parent), weight_name=lora_path.name)
        self._current_lora = lora_path
        logger.info("FluxEngine: LoRAロード完了")

    def generate(
        self,
        *,
        prompt: str,
        output_path: Path,
        lora_path: Path | None = None,
        width: int = 1024,
        height: int = 1024,
        num_inference_steps: int = 30,
        guidance_scale: float = 7.5,
        seed: int | None = None,
    ) -> Path:
        """アバター画像を生成する

        Args:
            prompt: 画像生成プロンプト
            output_path: 出力画像ファイルパス
            lora_path: LoRA safetensorsファイルパス (オプション)
            width: 画像幅 (ピクセル)
            height: 画像高さ (ピクセル)
            num_inference_steps: 推論ステップ数
            guidance_scale: ガイダンススケール
            seed: ランダムシード (再現性のため)

        Returns:
            生成した画像ファイルのパス

        Raises:
            RuntimeError: モデルが未ロードの場合
        """
        if self._pipe is None:
            raise RuntimeError("FluxEngine: モデルが未ロードです。先にload()を呼んでください")

        # シード固定
        generator: torch.Generator | None = None
        if seed is not None:
            generator = torch.Generator(device="cuda").manual_seed(seed)
            logger.info("FluxEngine: シード固定 (%d)", seed)

        # LoRA適用
        if lora_path is not None and lora_path != self._current_lora:
            self.load_lora(lora_path)

        # 出力ディレクトリ作成
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 画像生成
        logger.info(
            "FluxEngine: 画像生成開始 (prompt='%s', %dx%d, steps=%d)",
            prompt[:50],
            width,
            height,
            num_inference_steps,
        )
        result = self._pipe(
            prompt=prompt,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            generator=generator,
        )
        image = result.images[0]

        # 保存
        image.save(str(output_path))
        logger.info("FluxEngine: 画像保存完了 (%s)", output_path)

        return output_path
