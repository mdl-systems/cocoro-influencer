"""
Avatar Video Pipeline - メインオーケストレーター

3Dアバターから実写風AI動画を全自動生成するパイプラインの制御。
処理フロー:
  1. Blender: VRMモデル → ポーズ付き3Dレンダリング（RGB + Depth + Canny）
  2. ComfyUI (FLUX + ControlNet): 3Dレンダリング → 実写風画像
  3. ComfyUI (Wan 2.1 I2V): 実写画像 → 動画クリップ
  4. TTS: 台本テキスト → 音声ファイル
  5. ComfyUI (LivePortrait): 動画 + 音声 → リップシンク動画
  6. Editor (MoviePy + FFmpeg): シーン結合 → 最終MP4
"""

import argparse
import asyncio
import json
import logging
import sys
import time
import uuid
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import load_settings, PROJECT_ROOT

# ── ロギング設定 ──────────────────────────────────────────────
def setup_logging(level: str = "INFO"):
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "pipeline.log", encoding="utf-8"),
        ],
    )

logger = logging.getLogger("pipeline")


# ── データモデル ──────────────────────────────────────────────
@dataclass
class SceneSpec:
    """1シーンの仕様"""
    scene_id: str
    script_text: str                      # セリフ・ナレーション
    pose: str = "neutral"                 # ポーズ名 (pose_library.json参照)
    expression: str = "neutral"           # 表情名
    duration: float = 5.0                 # 秒
    camera_angle: str = "upper_body"      # カメラアングル (full_body, upper_body, close_up)
    background: Optional[str] = None      # 背景画像パス（オプション）
    appearance_prompt: str = "photorealistic, highly detailed, 8k resolution, cinematic lighting, 1girl, upper body, beautiful face, business suit"
    background_prompt: str = "in a modern office, bright lighting"
    negative_prompt: str = "anime, text, watermark, worst quality"


@dataclass
class JobSpec:
    """動画生成ジョブ全体の仕様"""
    job_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    avatar_path: str = ""                  # VRMモデルパス
    scenes: List[SceneSpec] = field(default_factory=list)
    bgm_path: Optional[str] = None        # BGMファイルパス
    output_path: str = "output/final.mp4"
    resolution: tuple = (1280, 720)       # 出力解像度


@dataclass
class PipelineResult:
    """パイプライン実行結果"""
    success: bool
    job_id: str
    output_path: Optional[str] = None
    elapsed_seconds: float = 0.0
    error: Optional[str] = None
    scene_results: List[dict] = field(default_factory=list)


# ── パイプラインステージ ────────────────────────────────────
class Pipeline:
    """メインパイプライン"""

    def __init__(self, settings=None):
        self.settings = settings or load_settings()
        self.work_dir = PROJECT_ROOT / "tmp" / f"job_{int(time.time())}"
        self._comfyui_runner = None
        self._tts_manager = None
        self._compositor = None

    def _get_comfyui_runner(self):
        if self._comfyui_runner is None:
            from comfyui.workflow_runner import WorkflowRunner
            self._comfyui_runner = WorkflowRunner(
                host=self.settings.comfyui.host,
                port=self.settings.comfyui.port,
            )
        return self._comfyui_runner

    def _get_tts_manager(self):
        if self._tts_manager is None:
            from tts.engine import TTSManager
            self._tts_manager = TTSManager(self.settings)
        return self._tts_manager

    def _get_compositor(self):
        if self._compositor is None:
            from editor.compositor import VideoCompositor
            self._compositor = VideoCompositor(
                ffmpeg_path=self.settings.ffmpeg.path,
                encoder=self.settings.ffmpeg.encoder,
                hwaccel=self.settings.ffmpeg.hwaccel,
                quality=self.settings.ffmpeg.quality,
            )
        return self._compositor

    async def run(self, job: JobSpec, approval_callback=None, progress_callback=None) -> PipelineResult:
        """パイプライン全体を実行"""
        start_time = time.time()
        self.work_dir = PROJECT_ROOT / "tmp" / f"job_{job.job_id}"
        self.work_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"╔════════════════════════════════════════════════╗")
        logger.info(f"║  パイプライン開始: Job {job.job_id}")
        logger.info(f"║  シーン数: {len(job.scenes)}")
        logger.info(f"║  アバター: {job.avatar_path}")
        logger.info(f"╚════════════════════════════════════════════════╝")

        result = PipelineResult(success=True, job_id=job.job_id)

        try:
            # ── ステージ1: 全シーンの3Dレンダリング ──
            logger.info("━━━ Stage 1/5: Blender 3Dレンダリング ━━━")
            if progress_callback: await progress_callback(10, "Stage 1: Blenderを用いて3Dポーズを出力中...")
            while True:
                render_outputs = await self._stage_blender(job)
                if approval_callback and not render_outputs[0].get("is_fallback", False):
                    action = await approval_callback("Stage1_Blender_3D", render_outputs[0]["rgb"])
                    if action == "retry": continue
                    if action == "reject": raise Exception("キャンセルされました(Stage 1)")
                break

            # ── ステージ2: AI実写化 (FLUX + ControlNet) ──
            logger.info("━━━ Stage 2/5: AI実写化 (FLUX + ControlNet) ━━━")
            if progress_callback: await progress_callback(30, "Stage 2: FLUX + ControlNet で実写化中... (1分〜2分)")
            while True:
                realify_outputs = await self._stage_realify(job, render_outputs)
                if approval_callback:
                    action = await approval_callback("Stage2_FLUX_実写化", realify_outputs[0]["image"])
                    if action == "retry": continue
                    if action == "reject": raise Exception("キャンセルされました(Stage 2)")
                break

            # ── ステージ3: TTS音声合成 ──
            logger.info("━━━ Stage 3/5: TTS音声合成 ━━━")
            if progress_callback: await progress_callback(50, "Stage 3: TTSエンジン (Style-Bert-VITS2) で音声合成中...")
            while True:
                audio_outputs = await self._stage_tts(job)
                if approval_callback:
                    action = await approval_callback("Stage3_音声合成", audio_outputs[0]["audio"])
                    if action == "retry": continue
                    if action == "reject": raise Exception("キャンセルされました(Stage 3)")
                break

            # ── ステージ4: AI動画生成 + リップシンク ──
            logger.info("━━━ Stage 4/5: AI動画生成 (Wan 2.1) + リップシンク ━━━")
            if progress_callback: await progress_callback(70, "Stage 4: Wan 2.1 動画生成中... 今しばらくお待ちください (約15〜20分)")
            
            while True:
                # Combine realify and audio outputs for stage 4
                combined_results = []
                for i, (r_out, a_out) in enumerate(zip(realify_outputs, audio_outputs)):
                    combined_results.append({
                        "scene_id": r_out["scene_id"],
                        "image": r_out["image"],
                        "audio": a_out["audio"],
                        "duration": a_out["duration"],
                    })

                video_outputs = await self._stage_video(job, combined_results)
                if approval_callback and video_outputs and "video" in video_outputs[0]:
                    action = await approval_callback("Stage4_Wan_動画生成", video_outputs[0]["video"])
                    if action == "retry": continue
                    if action == "reject": raise Exception("キャンセルされました(Stage 4)")
                break

            # ── ステージ5: 自動編集・結合 ──
            logger.info("━━━ Stage 5/5: 自動編集・結合 ━━━")
            if progress_callback: await progress_callback(95, "Stage 5: LivePortrait (リップシンク) 適用・エンコード中...")
            final_path = await self._stage_compose(job, video_outputs)

            elapsed = time.time() - start_time
            logger.info(f"✅ パイプライン完了: {final_path} ({elapsed:.1f}秒)")

            result.output_path = str(final_path)
            result.scene_results = video_outputs
            result.elapsed_seconds = elapsed
            return result

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"❌ パイプラインエラー: {e}", exc_info=True)
            return PipelineResult(
                success=False,
                job_id=job.job_id,
                elapsed_seconds=elapsed,
                error=str(e),
            )

    # ── 各ステージのプレースホルダー ──────────────────────────

    async def _stage_blender(self, job: JobSpec) -> List[dict]:
        """
        Blenderヘッドレスを使用してVRMアバターをレンダリング。
        各シーンに対して RGB, Depth, Canny 画像を出力。
        """
        import subprocess as sp

        blender_exe = self.settings.blender.path
        script_path = str(PROJECT_ROOT / "blender" / "render_avatar.py")
        outputs = []

        for i, scene in enumerate(job.scenes):
            scene_dir = self.work_dir / f"scene_{i:03d}" / "render"
            scene_dir.mkdir(parents=True, exist_ok=True)
            rgb_path = scene_dir / "rgb.png"
            depth_path = scene_dir / "depth.png"

            # もしアバター指定が画像（A: 画像アップロード機能）だった場合は、Blenderをスキップして画像をそのまま配置
            avatar_path_lower = str(job.avatar_path).lower()
            if avatar_path_lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
                logger.info(f"  [{i+1}/{len(job.scenes)}] カスタムキャラクター画像がアップロードされています。Blenderをスキップします。")
                import shutil
                shutil.copy(str(PROJECT_ROOT / job.avatar_path), str(rgb_path))
            else:
                logger.info(f"  [{i+1}/{len(job.scenes)}] ポーズ={scene.pose}, 表情={scene.expression}")

                cmd = [
                    blender_exe, "-b",
                    "--python", script_path, "--",
                    "--vrm", str(PROJECT_ROOT / job.avatar_path),
                    "--pose", scene.pose,
                    "--expression", scene.expression,
                    "--camera", scene.camera_angle,
                    "--output", str(scene_dir),
                    "--width", str(self.settings.blender.render_width),
                    "--height", str(self.settings.blender.render_height),
                    "--engine", f"BLENDER_{self.settings.blender.render_engine}",
                ]

                try:
                    result = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await result.communicate()
                    if result.returncode != 0:
                        logger.warning(f"  ⚠ Blenderレンダリング警告 (scene {i}): {stderr.decode(errors='replace')[:200]}")
                except FileNotFoundError:
                    logger.warning(f"  ⚠ Blender未検出: {blender_exe} - スキップ")

            # Blenderが使えない場合のフォールバック（テストモード用）
            is_fallback = False
            if not rgb_path.exists():
                import shutil
                fallback_candidates = [
                    Path(r"F:\ComfyUI\input\realify_s_000.png"),
                    Path(r"F:\ComfyUI\input\e2e_test_result.png"),
                    Path(r"F:\ComfyUI\input\test_avatar_rgb.png"),
                ]
                for candidate in fallback_candidates:
                    if candidate.exists():
                        shutil.copy(str(candidate), str(rgb_path))
                        logger.warning(f"  Blender出力なし -> フォールバック使用: {candidate.name}")
                        is_fallback = True
                        break

            if not depth_path.exists() and rgb_path.exists():
                import shutil
                shutil.copy(str(rgb_path), str(depth_path))  # depthも同じ画像で代替

            outputs.append({
                "scene_id": scene.scene_id,
                "rgb": str(rgb_path),
                "depth": str(depth_path),
                "canny": str(scene_dir / "canny.png"),
                "is_fallback": is_fallback,
            })

        logger.info(f"  → {len(outputs)} シーンのレンダリング完了")
        return outputs

    async def _stage_realify(self, job_spec: JobSpec, render_outputs: List[dict]) -> List[dict]:
        """
        ComfyUI (FLUX + ControlNet) で3Dレンダリングを実写化。
        """
        runner = self._get_comfyui_runner()
        outputs = []

        # ユーザーがカスタム画像（写真等）をアップロードした場合は、FLUX実写化をスキップしてその画像を全シーンで「固定」使用する
        avatar_path_lower = str(job_spec.avatar_path).lower()
        if avatar_path_lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
            logger.info("  👉 アップロードされたキャラクター画像を検知しました。FLUX実写化をスキップし、この画像を全シーンで固定使用します。")
            for render in render_outputs:
                outputs.append({
                    "scene_id": render["scene_id"],
                    "image": render["rgb"],
                })
            return outputs

        for i, render in enumerate(render_outputs):
            logger.info(f"  [{i+1}/{len(render_outputs)}] {render['scene_id']}")

            output_dir = str(Path(render["rgb"]).parent.parent / "realify")
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            scene_spec = next((s for s in job_spec.scenes if s.scene_id == render["scene_id"]), None)
            appearance_prompt = scene_spec.appearance_prompt if scene_spec else "photorealistic, highly detailed, 1girl, upper body, business suit"
            
            # 【レイヤー分離・人体精度向上対応】
            appearance_prompt += ", highly detailed photographic human model, real human anatomy, 8k resolution portrait, ultra realistic face, extremely detailed skin pores, masterpiece photography, ray tracing, sharp focus, isolated on a perfect solid bright green screen background, chroma key green #00FF00 flat background color"

            # Dummy image fallback check
            is_fallback = render.get("is_fallback", False)
            canny_s = 0.0 if is_fallback else 0.15
            depth_s = 0.0 if is_fallback else 0.45
            if is_fallback:
                logger.info(f"  [{i+1}] Blenderモデルが無い為、完全新規の顔(T2Iモード)を生成します。")

            try:
                result_path = await runner.run_realify(
                    input_image=render["rgb"],
                    depth_image=render["depth"],
                    scene_id=render["scene_id"],
                    output_dir=output_dir,
                    prompt=appearance_prompt,
                    cn_canny_strength=canny_s,
                    cn_depth_strength=depth_s
                )
                output_path = result_path
            except Exception as e:
                logger.warning(f"  ⚠ 実写化失敗 ({render['scene_id']}): {e}")
                output_path = render["rgb"]  # フォールバック: 元画像を使用

            outputs.append({
                "scene_id": render["scene_id"],
                "image": output_path,
            })

        logger.info(f"  → {len(outputs)} シーンの実写化完了")
        return outputs

    async def _stage_tts(self, job: JobSpec) -> List[dict]:
        """
        TTSエンジンで台本テキストを音声合成。
        """
        tts = self._get_tts_manager()
        outputs = []

        for i, scene in enumerate(job.scenes):
            logger.info(f"  [{i+1}/{len(job.scenes)}] '{scene.script_text[:30]}...'")

            audio_dir = self.work_dir / f"scene_{i:03d}" / "audio"
            audio_dir.mkdir(parents=True, exist_ok=True)
            audio_path = str(audio_dir / "voice.wav")

            try:
                result = await tts.synthesize(
                    text=scene.script_text,
                    output_path=audio_path,
                )
                duration = result.get("duration", scene.duration)
            except Exception as e:
                logger.warning(f"  ⚠ TTS失敗 ({scene.scene_id}): {e}")
                duration = scene.duration
                # 404エラーや後の結合エラーを防ぐため、エラー時はダミー(無音)WAVファイルを生成する
                import subprocess
                try:
                    subprocess.run(
                        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(duration), "-c:a", "pcm_s16le", audio_path],
                        capture_output=True,
                        check=True
                    )
                except Exception as ffmpeg_e:
                    logger.error(f"ダミーWAVの生成にも失敗しました: {ffmpeg_e}")

            outputs.append({
                "scene_id": scene.scene_id,
                "audio": audio_path,
                "duration": duration,
            })

        logger.info(f"  → {len(outputs)} シーンの音声合成完了")
        return outputs

    async def _stage_video(self, job_spec: JobSpec, scene_results: List[dict]) -> List[dict]:
        """
        Wan 2.1 I2V による映像生成 + LivePortrait リップシンク
        """
        runner = self._get_comfyui_runner()
        outputs = []

        for i, res in enumerate(scene_results):
            img = res.get("image")
            audio = res.get("audio")
            if not img:
                continue

            scene_id = res["scene_id"]
            logger.info(f"  [{i+1}/{len(scene_results)}] {scene_id}")

            video_dir = self.work_dir / f"scene_{i:03d}" / "video"
            video_dir.mkdir(parents=True, exist_ok=True)

            # フレーム数を音声の長さから計算 (16fps)
            duration = res.get("duration", 5.0)
            num_frames = min(33, max(33, int(duration * 16)))
            if num_frames % 2 == 0:
                num_frames += 1

            
            scene_spec = next((s for s in job_spec.scenes if s.scene_id == scene_id), None)
            wan_prompt = scene_spec.background_prompt if scene_spec and scene_spec.background_prompt else "subtle movement, breathing, natural, cinematic"

            try:
                # Step 1: Wan 2.1 I2V で画像→動画
                # ユーザーの要望に従い解像度を大幅に下げる(320x480等)ことでVRAMを解放し、クオリティと尺(80f等)を優先
                target_frames = int(duration * 16)
                if target_frames % 2 == 0:
                    target_frames += 1
                
                # 画角を下げてメモリを節約するため上限フレーム数を解除(1段階長めでも耐えられるように)
                i2v_path = await runner.run_i2v(
                    input_image=img,
                    scene_id=scene_id,
                    output_dir=str(video_dir),
                    width=320,
                    height=480,
                    num_frames=target_frames,
                )

                # Step 2: LivePortrait でリップシンク
                video_path = i2v_path  # デフォルトはリップシンク前の映像
                if audio and Path(audio).exists():
                    try:
                        lipsync_path = await runner.run_lipsync(
                            video_path=i2v_path,
                            audio_path=audio,
                            scene_id=scene_id,
                            output_dir=str(video_dir),
                        )
                        video_path = lipsync_path
                    except Exception as ls_e:
                        logger.warning(f"  リップシンク失敗 ({scene_id}): {ls_e} -> 代わりにWan2.1の純粋な動画を使用します")
            except Exception as e:
                logger.warning(f"  Wan2.1動画生成失敗 ({scene_id}): {e}")
                # フォールバック: ComfyUI output から最後に生成されたMP4を探す
                import glob
                fallback_mp4s = sorted(glob.glob(r"F:\ComfyUI\output\wan21_*.mp4"))
                if fallback_mp4s:
                    import shutil
                    fallback_dest = str(video_dir / "clip.mp4")
                    shutil.copy(fallback_mp4s[-1], fallback_dest)
                    video_path = fallback_dest
                    logger.warning(f"  フォールバック動画使用: {fallback_mp4s[-1]}")
                else:
                    video_path = str(video_dir / "clip.mp4")  # 存在しなければStage5でエラー

            outputs.append({
                "scene_id": scene_id,
                "video": video_path,
                "audio": audio,
            })

        logger.info(f"  → {len(outputs)} シーンの動画生成完了")
        return outputs

    async def _stage_compose(self, job: JobSpec, video_outputs: List[dict]) -> Path:
        """
        MoviePy + FFmpeg で全シーンを結合し、BGM・テロップを追加。
        """
        compositor = self._get_compositor()
        output_path = PROJECT_ROOT / job.output_path

        # SRT字幕を生成
        from editor.compositor import SubtitleGenerator
        srt_path = str(self.work_dir / "subtitles.srt")
        accumulated_time = 0.0
        srt_scenes = []
        for i, scene in enumerate(job.scenes):
            srt_scenes.append({
                "text": scene.script_text,
                "start": accumulated_time,
                "end": accumulated_time + scene.duration,
            })
            accumulated_time += scene.duration
        SubtitleGenerator.generate_srt(srt_scenes, srt_path)

        # 動画結合
        bg_image_path = getattr(job, "bg_image_path", None)
        if not bg_image_path:
            bg_image_path = str(PROJECT_ROOT / "assets" / "default_bg.jpg")
        
        result = await compositor.compose(
            scene_clips=video_outputs,
            output_path=str(output_path),
            bgm_path=job.bgm_path,
            srt_path=srt_path,
            resolution=job.resolution,
            bg_image_path=bg_image_path
        )

        logger.info(f"  → 最終動画: {result}")
        return Path(result)


# ── CLI エントリポイント ─────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description="Avatar Video Pipeline - 3Dアバターから実写風AI動画を全自動生成",
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        help="入力VRMモデルのパス",
    )
    parser.add_argument(
        "--script", "-s",
        type=str,
        help="台本JSONファイルのパス",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="output/final.mp4",
        help="出力MP4パス (default: output/final.mp4)",
    )
    parser.add_argument(
        "--duration", "-d",
        type=float,
        default=5.0,
        help="テスト動画の秒数 (default: 5.0)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="テストモードで実行（サンプルデータ使用）",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    settings = load_settings()
    setup_logging(settings.job.log_level)

    logger.info("Avatar Video Pipeline v0.1.0")
    logger.info(f"GPU VRAM制限: {settings.gpu.vram_limit}MB")
    logger.info(f"ComfyUI: {settings.comfyui.base_url}")

    # テストモード: サンプルジョブを生成
    if args.test:
        job = JobSpec(
            avatar_path=args.input or "models/sample_avatar.vrm",
            scenes=[
                SceneSpec(
                    scene_id="test_001",
                    script_text="こんにちは、私はAIが生成したアバターです。",
                    pose="greeting",
                    expression="smile",
                    duration=args.duration,
                ),
            ],
            output_path=args.output,
        )
    elif args.script:
        # 台本JSONから読み込み
        with open(args.script, "r", encoding="utf-8") as f:
            script_data = json.load(f)
        job = JobSpec(
            avatar_path=script_data.get("avatar", args.input or ""),
            scenes=[
                SceneSpec(**s) for s in script_data.get("scenes", [])
            ],
            bgm_path=script_data.get("bgm"),
            output_path=args.output,
        )
    else:
        logger.error("--input または --script を指定してください")
        sys.exit(1)

    pipeline = Pipeline(settings)
    result = await pipeline.run(job)

    if result.success:
        logger.info(f"🎬 完成: {result.output_path} ({result.elapsed_seconds:.1f}秒)")
    else:
        logger.error(f"💥 失敗: {result.error}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
