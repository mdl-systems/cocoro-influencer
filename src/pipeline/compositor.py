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
    # B-2 トランジション
    transition: str = "none"             # "none"/"fade"/"wipeleft"/"wiperight"/"dissolve"/"slideleft"
    transition_duration: float = 0.5     # トランジション時間 (秒)
    # B-3 ウォーターマーク/ロゴ
    watermark_path: Path | None = None   # ウォーターマーク画像パス
    watermark_position: str = "bottom-right"  # 位置
    watermark_scale: float = 0.15        # 幅比率 (動画幅に対する割合)
    watermark_opacity: float = 0.85      # 不透明度 (0.0=透明, 1.0=不透明)


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

    # 日本語フォントパス候補 (Debian感常パス)
    _JP_FONTS: list[str] = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    ]

    def _get_clip_duration(self, clip_path: Path) -> float:
        """ffprobe\u3067\u30af\u30ea\u30c3\u30d7\u306e\u5b9f\u969b\u306e\u9577\u3055(\u79d2)\u3092\u53d6\u5f97\u3059\u308b"""
        for probe_args in [
            ["-select_streams", "v:0", "-show_entries", "stream=duration"],
            ["-show_entries", "format=duration"],
        ]:
            result = _sp.run(
                ["ffprobe", "-v", "error", *probe_args,
                 "-of", "default=noprint_wrappers=1:nokey=1", str(clip_path)],
                capture_output=True, text=True,
            )
            try:
                val = float(result.stdout.strip())
                if val > 0:
                    return val
            except (ValueError, AttributeError):
                pass
        logger.warning("Compositor: duration\u53d6\u5f97\u5931\u6557 %s \u2192 5.0\u79d2\u3068\u4eee\u5b9a", clip_path.name)
        return 5.0

    def _compose_video_with_xfade(
        self,
        norm_paths: list[Path],
        out_path: Path,
        transition: str,
        transition_duration: float,
    ) -> None:
        """xfade\u30d5\u30a3\u30eb\u30bf\u30fc\u3067\u30c8\u30e9\u30f3\u30b8\u30b7\u30e7\u30f3\u4ed8\u304d\u30d3\u30c7\u30aa\u3092\u7d50\u5408\u3059\u308b (B-2)"""
        import shutil as _sh
        if len(norm_paths) == 1:
            _sh.copy2(str(norm_paths[0]), str(out_path))
            return

        durations = [self._get_clip_duration(p) for p in norm_paths]
        logger.info("Compositor: xfade \u30af\u30ea\u30c3\u30d7\u9577 = %s", [f"{d:.2f}s" for d in durations])

        # transition_duration \u304c\u30af\u30ea\u30c3\u30d7\u9577\u306e 40% \u4ee5\u4e0a\u306b\u306a\u3089\u306a\u3044\u3088\u3046\u30af\u30e9\u30f3\u30d7
        td = min(transition_duration, min(d * 0.4 for d in durations))

        inputs: list[str] = []
        for p in norm_paths:
            inputs += ["-i", str(p)]

        filter_parts: list[str] = []
        prev_tag = "[0:v]"
        cumulative_dur = durations[0]

        for i in range(1, len(norm_paths)):
            is_last = (i == len(norm_paths) - 1)
            offset = max(0.01, cumulative_dur - td)
            dst_tag = "[outv]" if is_last else f"[xf{i}]"
            filter_parts.append(
                f"{prev_tag}[{i}:v]xfade=transition={transition}:"
                f"duration={td:.3f}:offset={offset:.3f}{dst_tag}"
            )
            cumulative_dur += durations[i] - td
            prev_tag = dst_tag

        filter_complex = ";".join(filter_parts)
        logger.debug("Compositor: xfade filter = %s", filter_complex)
        self._run_ffmpeg([
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-c:v", "libx264", "-preset", "fast",
            "-an",
            str(out_path), "-y",
        ])
        logger.info("Compositor: xfade\u30d3\u30c7\u30aa\u7d50\u5408\u5b8c\u4e86 (%d clips) \u2192 %s", len(norm_paths), out_path.name)

    def _watermark_overlay_str(self, position: str) -> str:
        """\u30a6\u30a9\u30fc\u30bf\u30fc\u30de\u30fc\u30af\u306eoverlay\u4f4d\u7f6e\u5f0f (FFmpeg overlay x:y \u5f62\u5f0f)"""
        return {
            "bottom-right": "W-w-24:H-h-24",
            "bottom-left":  "24:H-h-24",
            "top-right":    "W-w-24:24",
            "top-left":     "24:24",
            "center":       "(W-w)/2:(H-h)/2",
        }.get(position, "W-w-24:H-h-24")

    def _get_jp_font(self) -> str | None:
        """Japaneseフォントパスを返す。見つからなければ None"""
        from pathlib import Path as _P
        for p in self._JP_FONTS:
            if _P(p).exists():
                return p
        return None

    def _build_drawtext_filter(self, captions: list[Caption], fmt: dict) -> str:
        """テロップ用 drawtext フィルタ文字列を構築する

        日本語フォントを自動検出し、半透明黒ボックス付き字幕を追加する
        """
        font_path = self._get_jp_font()
        font_arg = f"fontfile={font_path}:" if font_path else ""

        filters = []
        for caption in captions:
            y_pos = self._caption_y_position(caption.position, fmt["height"])
            # シングルクォートとコロンをエスケープ
            safe_text = (caption.text
                         .replace("\\", "\\\\")
                         .replace("'", "\\u2019")
                         .replace(":", "\\:"))
            filters.append(
                f"drawtext={font_arg}"
                f"text='{safe_text}':"
                f"fontsize={caption.font_size}:"
                f"fontcolor={caption.font_color}:"
                f"x=(w-text_w)/2:y={y_pos}:"
                f"box=1:boxcolor=black@0.55:boxborderw=10:"
                f"enable='between(t,{caption.start_time},{caption.end_time})'"
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

        # \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        # Step 2: \u30d3\u30c7\u30aa\u7d50\u5408 (B-2: xfade\u3042\u308a/\u306a\u3057\u5206\u5c90)
        # \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        video_only_path = tmp_dir / "_video_only.mp4"
        use_xfade = (
            config.transition and config.transition != "none"
            and len(norm_paths) > 1
        )
        if use_xfade:
            self._compose_video_with_xfade(
                norm_paths, video_only_path,
                config.transition, config.transition_duration,
            )
            logger.info("Compositor: xfade\u30c8\u30e9\u30f3\u30b8\u30b7\u30e7\u30f3\u7d50\u5408\u5b8c\u4e86 (%d clips)", len(norm_paths))
        else:
            # concat demuxer \u3067\u30d3\u30c7\u30aa\u7d50\u5408\uff08stream copy\u3001\u9ad8\u901f\uff09
            concat_list_path = tmp_dir / "_concat_list.txt"
            concat_list_path.write_text(
                "\n".join(f"file '{p.resolve()}'" for p in norm_paths),
                encoding="utf-8",
            )
            self._run_ffmpeg([
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list_path),
                "-c", "copy",
                str(video_only_path), "-y",
            ])
            logger.info("Compositor: \u30d3\u30c7\u30aa\u7d50\u5408\u5b8c\u4e86 (%d clips)", len(norm_paths))

        # \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        # Step 3: \u97f3\u58f0\u7d50\u5408
        # \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        audio_files = self._collect_audio_files(config)
        merged_audio_path = tmp_dir / "_merged_audio.aac"
        self._concat_audio(audio_files, merged_audio_path)
        logger.info("Compositor: \u97f3\u58f0\u7d50\u5408\u5b8c\u4e86")

        # \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        # Step 4: BGM\u30df\u30c3\u30af\u30b9\uff08\u30aa\u30d7\u30b7\u30e7\u30f3\uff09
        # \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
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
            logger.info("Compositor: BGM\u30df\u30c3\u30af\u30b9\u5b8c\u4e86")
        else:
            final_audio_path = merged_audio_path

        # \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        # Step 5: \u30a6\u30a9\u30fc\u30bf\u30fc\u30de\u30fc\u30af (B-3) + \u30c6\u30ed\u30c3\u30d7 + \u6700\u7d42\u30de\u30fc\u30b8
        # \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        has_wm = (config.watermark_path is not None and config.watermark_path.exists())
        has_caps = bool(config.captions)

        if has_wm:
            wm_scale = config.watermark_scale
            wm_alpha = config.watermark_opacity
            wm_pos   = self._watermark_overlay_str(config.watermark_position)
            # [0:v]=\u30d3\u30c7\u30aa, [1:a]=\u97f3\u58f0, [2:v]=\u30ed\u30b4
            wm_filter = (
                f"[2:v]scale=iw*{wm_scale}:-1,format=rgba,"
                f"colorchannelmixer=aa={wm_alpha}[wm];"
                f"[0:v][wm]overlay={wm_pos}"
            )
            if has_caps:
                drawtext = self._build_drawtext_filter(config.captions, fmt)
                filter_complex = f"{wm_filter}[wmv];[wmv]{drawtext}[outv]"
            else:
                filter_complex = f"{wm_filter}[outv]"

            self._run_ffmpeg([
                "-i", str(video_only_path),
                "-i", str(final_audio_path),
                "-i", str(config.watermark_path),
                "-filter_complex", filter_complex,
                "-map", "[outv]", "-map", "1:a",
                "-c:v", "libx264", "-preset", "fast",
                "-b:v", fmt["vbitrate"],
                "-c:a", "aac", "-b:a", fmt["abitrate"],
                "-movflags", "+faststart",
                "-shortest",
                str(config.output_path), "-y",
            ])

        elif has_caps:
            drawtext = self._build_drawtext_filter(config.captions, fmt)
            self._run_ffmpeg([
                "-i", str(video_only_path),
                "-i", str(final_audio_path),
                "-vf", drawtext,
                "-c:v", "libx264", "-preset", "fast",
                "-b:v", fmt["vbitrate"],
                "-c:a", "aac", "-b:a", fmt["abitrate"],
                "-movflags", "+faststart",
                "-shortest",
                str(config.output_path), "-y",
            ])

        else:
            # \u5b57\u5e55\u30fb\u30ed\u30b4\u306a\u3057: \u30b3\u30d4\u30fc\u6e21\u3057\u3067\u6700\u901f
            self._run_ffmpeg([
                "-i", str(video_only_path),
                "-i", str(final_audio_path),
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", fmt["abitrate"],
                "-movflags", "+faststart",
                "-shortest",
                str(config.output_path), "-y",
            ])

        logger.info("Compositor: \u5408\u6210\u5b8c\u4e86 \u2192 %s", config.output_path)

        # \u4e2d\u9593\u30d5\u30a1\u30a4\u30eb\u306e\u30af\u30ea\u30fc\u30f3\u30a2\u30c3\u30d7
        self._cleanup_temp_files(norm_paths, [
            tmp_dir / "_concat_list.txt",  # xfade\u6642\u306f\u5b58\u5728\u3057\u306a\u3044\u304c\u7121\u8996\u3055\u308c\u308b
            video_only_path,
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
