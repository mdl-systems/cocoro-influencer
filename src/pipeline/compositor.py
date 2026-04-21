"""compositor.py: FFmpegによる動画合成モジュール

複数の動画クリップを結合し、BGMとテロップを付けて最終動画を生成する。
subprocess経由でFFmpegを直接制御してSAR不一致エラーを回避する。

## SAR不一致問題について
Kling AI → 960x960 (SAR=1:1 でも出力解像度が異なる)
Wav2Lip  → 720x1280 (SAR=1:1)
→ concat前に scale + pad + setsar=1 で完全正規化する。
"""

import logging
import subprocess as _sp
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# 出力フォーマット別のデフォルト設定
# 小注: Wan2.1 I2V-14B-480P のネイティブ解像度は 480x832 (9:16縦動画)
# youtube形式は縦動画(480x832)を横(1920x1080)に変換するため黒帯大、非推奨。
OUTPUT_FORMATS: dict[str, dict] = {
    "youtube": {
        # 警告: Wan2.1出力(480x832縦動画)を横1920x1080にリサイズするため左右に大きな黒帯が入る。
        # 縦動画コンテンツ少なくとも "shorts" または "instagram" を使うことを推奨。
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "vbitrate": "8000k",
        "abitrate": "192k",
    },
    "shorts": {
        # TikTok / YouTube Shorts 推奨 (Wan2.1ネイティブ解像度と一致)
        "width": 480,
        "height": 832,
        "fps": 16,   # Wan2.1が16fpsネイティブ生成のため、不要なフレーム補間を回避
        "vbitrate": "4000k",
        "abitrate": "128k",
    },
    "instagram": {
        # Instagram 正方動画用 (1:1アスペクト比)
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
    output_format: str = "shorts"         # 出力フォーマット (default: shorts/縦動画)
    bgm_volume: float = 0.15             # BGM音量 (0.0〜1.0)
    fade_duration: float = 0.5           # クリップ間フェード時間 (秒) ※現在未使用


class Compositor:
    """FFmpegによる動画合成クラス

    複数クリップの結合・BGM追加・テロップ追加を行う。
    subprocess経由でFFmpegを直接制御し、SAR不一致を確実に解決する。
    """

    def _run_ffmpeg(self, args: list[str]) -> None:
        """FFmpegコマンドを実行しエラー時は詳細ログを出す"""
        cmd = ["ffmpeg"] + args
        logger.debug("FFmpeg: %s", " ".join(cmd))
        result = _sp.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("FFmpeg stderr:\n%s", result.stderr[-3000:])
            raise RuntimeError(
                f"FFmpeg実行エラー (code={result.returncode})\n{result.stderr[-500:]}"
            )

    def _build_normalize_filter(self, fmt: dict) -> str:
        """クリップ正規化用 vf フィルタ文字列を構築する。

        scale + pad + setsar=1 の組み合わせで:
        - 解像度を指定サイズに統一
        - アスペクト比を維持しつつ黒帯でパディング
        - SAR (Sample Aspect Ratio) を 1:1 に固定
        - ピクセルフォーマットを yuv420p に統一 (libx264 必須)
        """
        w, h, fps = fmt["width"], fmt["height"], fmt["fps"]
        return (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,"
            f"fps={fps},"
            f"format=yuv420p"
        )

    def _normalize_clip(self, clip_path: Path, out_path: Path, fmt: dict) -> None:
        """1クリップを正規化（解像度・FPS・SAR・ピクセルフォーマット統一）

        映像のみを出力（音声は別途処理）する。
        """
        vf = self._build_normalize_filter(fmt)
        self._run_ffmpeg([
            "-i", str(clip_path),
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "fast",
            "-an",   # 音声なし（後で別途マージ）
            str(out_path), "-y",
        ])
        logger.info("Compositor: 正規化完了 %s → %s", clip_path.name, out_path.name)

    def _collect_audio_files(self, config: CompositeConfig) -> list[Path]:
        """クリップに対応する音声ファイル(WAV優先)を収集する"""
        audio_files: list[Path] = []
        for clip_path in config.clips:
            # scene_XXX_clip.mp4 → scene_XXX_voice.wav を探す
            wav_path = clip_path.parent / (clip_path.stem.replace("_clip", "_voice") + ".wav")
            if wav_path.exists():
                audio_files.append(wav_path)
                logger.debug("Compositor: 音声WAV使用 %s", wav_path.name)
            else:
                # WAVがなければクリップ内の音声を使用
                audio_files.append(clip_path)
                logger.debug("Compositor: クリップ音声使用 %s", clip_path.name)
        return audio_files

    def _concat_audio(self, audio_files: list[Path], out_path: Path) -> None:
        """音声ファイルを結合してWAV/AACを出力する"""
        if len(audio_files) == 1:
            # 1ファイルならコピーのみ
            self._run_ffmpeg([
                "-i", str(audio_files[0]),
                "-c:a", "aac", "-b:a", "192k",
                str(out_path), "-y",
            ])
        else:
            # filter_complex で amix 結合
            inputs: list[str] = []
            for af in audio_files:
                inputs += ["-i", str(af)]
            filter_parts = "".join(f"[{i}:a]" for i in range(len(audio_files)))
            concat_filter = f"{filter_parts}concat=n={len(audio_files)}:v=0:a=1[outa]"
            self._run_ffmpeg([
                *inputs,
                "-filter_complex", concat_filter,
                "-map", "[outa]",
                "-c:a", "aac", "-b:a", "192k",
                str(out_path), "-y",
            ])

    def _build_drawtext_filter(self, captions: list[Caption], fmt: dict) -> str:
        """テロップ用 drawtext フィルタ文字列を構築する"""
        filters = []
        for caption in captions:
            y_pos = self._caption_y_position(caption.position, fmt["height"])
            # シングルクォートをエスケープ
            safe_text = caption.text.replace("'", "\\'")
            filters.append(
                f"drawtext=text='{safe_text}':"
                f"fontsize={caption.font_size}:"
                f"fontcolor={caption.font_color}:"
                f"x=(w-text_w)/2:y={y_pos}:"
                f"enable='between(t,{caption.start_time},{caption.end_time})':"
                f"shadowx=2:shadowy=2:shadowcolor=black"
            )
        return ",".join(filters)

    def _caption_y_position(self, position: str, height: int) -> str:
        """テロップのY座標を計算する"""
        if position == "top":
            return "50"
        elif position == "center":
            return "(h-text_h)/2"
        else:  # bottom
            return f"{height - 120}"

    def compose(self, config: CompositeConfig) -> Path:
        """動画合成を実行する

        処理フロー:
        1. 各クリップを正規化（解像度・FPS・SAR統一）→ 中間ファイル
        2. concat demuxer でビデオ結合（音声なし）
        3. 対応するWAVから音声を結合
        4. BGMミックス（設定されている場合）
        5. テロップ追加（設定されている場合）
        6. ビデオ + 音声 → 最終出力

        Args:
            config: 合成設定

        Returns:
            生成した最終動画ファイルのパス

        Raises:
            FileNotFoundError: 入力ファイルが存在しない場合
            ValueError: 不正なフォーマット名の場合
            RuntimeError: FFmpeg実行エラー
        """
        # 入力検証
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

        fmt = OUTPUT_FORMATS[config.output_format]
        config.output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_dir = config.output_path.parent

        logger.info(
            "Compositor: 合成開始 (clips=%d, format=%s, %dx%d@%d)",
            len(config.clips), config.output_format,
            fmt["width"], fmt["height"], fmt["fps"],
        )

        # ─────────────────────────────────────────────────
        # Step 1: 各クリップを正規化（SAR=1固定）
        # ─────────────────────────────────────────────────
        norm_paths: list[Path] = []
        for i, clip_path in enumerate(config.clips):
            norm_path = tmp_dir / f"_norm_{i:03d}.mp4"
            self._normalize_clip(clip_path, norm_path, fmt)
            norm_paths.append(norm_path)

        # ─────────────────────────────────────────────────
        # Step 2: concat demuxer でビデオ結合（stream copy）
        # ─────────────────────────────────────────────────
        concat_list_path = tmp_dir / "_concat_list.txt"
        concat_list_path.write_text(
            "\n".join(f"file '{p.resolve()}'" for p in norm_paths),
            encoding="utf-8",
        )
        video_only_path = tmp_dir / "_video_only.mp4"
        self._run_ffmpeg([
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list_path),
            "-c", "copy",
            str(video_only_path), "-y",
        ])
        logger.info("Compositor: ビデオ結合完了 (%d clips)", len(norm_paths))

        # ─────────────────────────────────────────────────
        # Step 3: 音声結合
        # ─────────────────────────────────────────────────
        audio_files = self._collect_audio_files(config)
        merged_audio_path = tmp_dir / "_merged_audio.aac"
        self._concat_audio(audio_files, merged_audio_path)
        logger.info("Compositor: 音声結合完了")

        # ─────────────────────────────────────────────────
        # Step 4: BGMミックス（オプション）
        # ─────────────────────────────────────────────────
        if config.bgm_path is not None:
            mixed_audio_path = tmp_dir / "_mixed_audio.aac"
            self._run_ffmpeg([
                "-i", str(merged_audio_path),
                "-i", str(config.bgm_path),
                "-filter_complex",
                f"[1:a]volume={config.bgm_volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first[outa]",
                "-map", "[outa]",
                "-c:a", "aac", "-b:a", fmt["abitrate"],
                str(mixed_audio_path), "-y",
            ])
            final_audio_path = mixed_audio_path
            logger.info("Compositor: BGMミックス完了")
        else:
            final_audio_path = merged_audio_path

        # ─────────────────────────────────────────────────
        # Step 5: テロップ + 最終マージ
        # ─────────────────────────────────────────────────
        vf_args: list[str] = []

        if config.captions:
            drawtext = self._build_drawtext_filter(config.captions, fmt)
            vf_args = ["-vf", drawtext]

        self._run_ffmpeg([
            "-i", str(video_only_path),
            "-i", str(final_audio_path),
            *vf_args,
            "-c:v", "libx264" if vf_args else "copy",
            "-c:a", "aac",
            "-b:v", fmt["vbitrate"],
            "-b:a", fmt["abitrate"],
            "-movflags", "+faststart",
            "-shortest",
            str(config.output_path), "-y",
        ])

        logger.info("Compositor: 合成完了 → %s", config.output_path)

        # 中間ファイルのクリーンアップ
        self._cleanup_temp_files(norm_paths, [
            concat_list_path, video_only_path,
            merged_audio_path,
            tmp_dir / "_mixed_audio.aac",
        ])

        return config.output_path

    def _cleanup_temp_files(self, norm_paths: list[Path], others: list[Path]) -> None:
        """合成後の中間ファイルを削除する"""
        for p in norm_paths + others:
            try:
                if p.exists():
                    p.unlink()
            except Exception as exc:
                logger.warning("Compositor: 中間ファイル削除失敗 %s (%s)", p, exc)
