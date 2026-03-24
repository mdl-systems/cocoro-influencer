"""compositor.py: FFmpegによる動画合成モジュール

複数の動画クリップを結合し、BGMとテロップを付けて最終動画を生成する。
ffmpeg-pythonを使用してPythonからFFmpegを制御する。
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# 出力フォーマット別のデフォルト設定
OUTPUT_FORMATS: dict[str, dict] = {
    "youtube": {
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "vbitrate": "8000k",
        "abitrate": "192k",
    },
    "shorts": {
        "width": 1080,
        "height": 1920,
        "fps": 60,
        "vbitrate": "6000k",
        "abitrate": "128k",
    },
    "instagram": {
        "width": 1080,
        "height": 1080,
        "fps": 30,
        "vbitrate": "4000k",
        "abitrate": "128k",
    },
}


@dataclass
class Caption:
    """テロップ設定"""

    text: str
    start_time: float  # 秒
    end_time: float    # 秒
    font_size: int = 48
    font_color: str = "white"
    position: str = "bottom"  # "bottom" | "top" | "center"


@dataclass
class CompositeConfig:
    """動画合成設定"""

    clips: list[Path]                     # 入力クリップパスのリスト
    output_path: Path                     # 出力ファイルパス
    bgm_path: Path | None = None          # BGMファイルパス (オプション)
    captions: list[Caption] = field(default_factory=list)  # テロップリスト
    output_format: str = "youtube"        # 出力フォーマット
    bgm_volume: float = 0.15             # BGM音量 (0.0〜1.0)
    fade_duration: float = 0.5           # クリップ間フェード時間 (秒)


class Compositor:
    """FFmpegによる動画合成クラス

    複数クリップの結合・BGM追加・テロップ追加を行う。
    """

    def compose(self, config: CompositeConfig) -> Path:
        """動画合成を実行する

        Args:
            config: 合成設定

        Returns:
            生成した最終動画ファイルのパス

        Raises:
            FileNotFoundError: 入力ファイルが存在しない場合
            ValueError: 不正なフォーマット名の場合
            RuntimeError: FFmpeg実行エラー
        """
        # 入力ファイルの存在確認
        for clip_path in config.clips:
            if not clip_path.exists():
                raise FileNotFoundError(f"クリップが見つかりません: {clip_path}")

        if config.bgm_path is not None and not config.bgm_path.exists():
            raise FileNotFoundError(f"BGMファイルが見つかりません: {config.bgm_path}")

        if config.output_format not in OUTPUT_FORMATS:
            raise ValueError(
                f"不正なフォーマット: '{config.output_format}'. "
                f"使用可能: {list(OUTPUT_FORMATS.keys())}"
            )

        import ffmpeg  # Phase 2依存: ffmpeg-pythonが必要

        fmt = OUTPUT_FORMATS[config.output_format]
        config.output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Compositor: 合成開始 (clips=%d, format=%s, output=%s)",
            len(config.clips),
            config.output_format,
            config.output_path,
        )

        # 各クリップを正規化 (解像度・FPS統一)
        normalized_inputs = []
        for clip_path in config.clips:
            stream = (
                ffmpeg
                .input(str(clip_path))
                .video
                .filter("scale", fmt["width"], fmt["height"], force_original_aspect_ratio="decrease")
                .filter("pad", fmt["width"], fmt["height"], "(ow-iw)/2", "(oh-ih)/2")
                .filter("fps", fps=fmt["fps"])
            )
            normalized_inputs.append(stream)

        # クリップを結合
        if len(normalized_inputs) > 1:
            video_stream = ffmpeg.concat(*normalized_inputs, v=1, a=0)
        else:
            video_stream = normalized_inputs[0]

        # テロップ追加
        for caption in config.captions:
            y_pos = self._get_caption_y_position(caption.position, fmt["height"])
            video_stream = video_stream.drawtext(
                text=caption.text,
                fontsize=caption.font_size,
                fontcolor=caption.font_color,
                x="(w-text_w)/2",
                y=y_pos,
                enable=f"between(t,{caption.start_time},{caption.end_time})",
                shadowx=2,
                shadowy=2,
                shadowcolor="black",
            )

        # 音声ストリーム処理
        audio_streams = []
        for clip_path in config.clips:
            try:
                audio_stream = ffmpeg.input(str(clip_path)).audio
                audio_streams.append(audio_stream)
            except Exception:
                pass  # 音声なしクリップはスキップ

        if audio_streams:
            if len(audio_streams) > 1:
                audio_stream = ffmpeg.concat(*audio_streams, v=0, a=1)
            else:
                audio_stream = audio_streams[0]
        else:
            audio_stream = ffmpeg.anullsrc(r=44100, cl="stereo")

        # BGMミックス
        if config.bgm_path is not None:
            bgm_stream = (
                ffmpeg
                .input(str(config.bgm_path), stream_loop=-1)
                .audio
                .filter("volume", config.bgm_volume)
            )
            audio_stream = ffmpeg.filter(
                [audio_stream, bgm_stream],
                "amix",
                inputs=2,
                duration="first",
            )

        # 出力
        try:
            (
                ffmpeg
                .output(
                    video_stream,
                    audio_stream,
                    str(config.output_path),
                    vcodec="libx264",
                    acodec="aac",
                    video_bitrate=fmt["vbitrate"],
                    audio_bitrate=fmt["abitrate"],
                    pix_fmt="yuv420p",
                )
                .overwrite_output()
                .run(quiet=True)
            )
        except ffmpeg.Error as e:
            raise RuntimeError(f"FFmpeg実行エラー: {e.stderr.decode()}") from e

        logger.info("Compositor: 合成完了 (%s)", config.output_path)
        return config.output_path

    def _get_caption_y_position(self, position: str, height: int) -> str:
        """テロップのY座標を計算する"""
        if position == "top":
            return "50"
        elif position == "center":
            return "(h-text_h)/2"
        else:  # bottom
            return f"{height - 120}"
