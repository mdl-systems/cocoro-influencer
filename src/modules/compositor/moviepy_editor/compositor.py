"""
動画コンポジター - MoviePy + FFmpeg

シーン結合・BGM・テロップ・NVENCエンコードの自動処理。
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("editor.compositor")


class VideoCompositor:
    def __init__(self, ffmpeg_path="ffmpeg", encoder="libx264", hwaccel=None, quality=23):
        self.ffmpeg_path = ffmpeg_path
        self.encoder = encoder
        self.hwaccel = hwaccel
        self.quality = quality

    async def compose(self, scene_clips, output_path, bgm_path=None, srt_path=None, resolution=(1280,720), bg_image_path=None):
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        work_dir = output.parent / "_work"
        work_dir.mkdir(exist_ok=True)
        logger.info(f"結合開始: {len(scene_clips)}シーン → {output_path}")

        prepared = []
        for i, clip in enumerate(scene_clips):
            out = await self._prepare_clip(clip, str(work_dir / f"p_{i:03d}.mp4"), resolution, bg_image_path)
            prepared.append(out)

        merged = prepared[0] if len(prepared) == 1 else str(work_dir / "merged.mp4")
        if len(prepared) > 1:
            await self._concat(prepared, merged)

        if bgm_path:
            bgm_out = str(work_dir / "bgm.mp4")
            await self._add_bgm(merged, bgm_path, bgm_out)
            merged = bgm_out

        if srt_path:
            srt_out = str(work_dir / "srt.mp4")
            await self._burn_srt(merged, srt_path, srt_out)
            merged = srt_out

        await self._final_encode(merged, str(output))
        logger.info(f"✅ 完了: {output}")
        return str(output)

    async def _prepare_clip(self, clip, output, resolution, bg_image_path=None):
        cmd = [self.ffmpeg_path, "-y"]
        if self.hwaccel:
            cmd += ["-hwaccel", self.hwaccel]
            
        w, h = resolution
        
        if bg_image_path and Path(bg_image_path).exists():
            cmd += ["-loop", "1", "-i", str(bg_image_path)]
            cmd += ["-i", clip["video"]]
            
            has_audio = False
            if clip.get("audio") and Path(clip["audio"]).exists():
                cmd += ["-i", clip["audio"]]
                has_audio = True
                
            vf = (
                f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:-1:-1[bg];"
                f"[1:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:-1:-1,"
                f"chromakey=0x00FF00:0.15:0.1[fg];"
                f"[bg][fg]overlay=shortest=1[outv]"
            )
            cmd += ["-filter_complex", vf, "-map", "[outv]"]
            if has_audio:
                cmd += ["-map", "2:a"]
            cmd += ["-shortest"]
        else:
            cmd += ["-i", clip["video"]]
            if clip.get("audio") and Path(clip["audio"]).exists():
                cmd += ["-i", clip["audio"], "-shortest"]
            cmd += ["-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:-1:-1"]

        cmd += ["-c:v", self.encoder, "-preset", "fast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", output]
        await self._run(cmd)
        return output

    async def _concat(self, clips, output):
        list_file = Path(output).parent / "list.txt"
        list_file.write_text("\n".join(f"file '{c}'" for c in clips), encoding="utf-8")
        await self._run([
            self.ffmpeg_path, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c:v", self.encoder, "-preset", "fast", "-pix_fmt", "yuv420p", "-c:a", "aac", output,
        ])

    async def _add_bgm(self, video, bgm, output, vol=0.15):
        await self._run([
            self.ffmpeg_path, "-y", "-i", video, "-i", bgm,
            "-filter_complex", f"[1:a]volume={vol}[b];[0:a][b]amix=inputs=2:duration=first[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", output,
        ])

    async def _burn_srt(self, video, srt, output):
        srt_e = srt.replace("\\", "/").replace(":", "\\:")
        await self._run([
            self.ffmpeg_path, "-y", "-i", video,
            "-vf", f"subtitles='{srt_e}':force_style='FontSize=24,PrimaryColour=&HFFFFFF,Outline=2'",
            "-c:v", self.encoder, "-c:a", "copy", output,
        ])

    async def _final_encode(self, inp, output):
        await self._run([
            self.ffmpeg_path, "-y", "-i", inp,
            "-c:v", self.encoder, "-preset", "slow", "-crf", str(self.quality), "-pix_fmt", "yuv420p",
            "-b:v", "8M", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", output,
        ])

    async def _run(self, cmd):
        logger.debug(f"FFmpeg: {' '.join(cmd)}")
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg error ({proc.returncode}): {stderr.decode(errors='replace')}")


class SubtitleGenerator:
    @staticmethod
    def generate_srt(scenes, output_path, offset=0.0):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for i, s in enumerate(scenes, 1):
                st = s.get("start", 0) + offset
                en = s.get("end", st + 5) + offset
                f.write(f"{i}\n{SubtitleGenerator._fmt(st)} --> {SubtitleGenerator._fmt(en)}\n{s.get('text','')}\n\n")
        return output_path

    @staticmethod
    def _fmt(sec):
        h, m, s, ms = int(sec//3600), int(sec%3600//60), int(sec%60), int(sec%1*1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
