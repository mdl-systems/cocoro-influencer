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
        # [ハイブリッド] ComfyUIモジュールは今後使用せず、APIモジュールに移行します。
        return None

    def _get_tts_manager(self):
        if self._tts_manager is None:
            from src.modules.voice_gen.local_tts.engine import TTSManager
            self._tts_manager = TTSManager(self.settings)
        return self._tts_manager

    def _get_compositor(self):
        if self._compositor is None:
            from src.modules.compositor.moviepy_editor.compositor import VideoCompositor
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
        [ハイブリッド移行対応]
        現在はまだFal.ai等のFLUX APIが未構成のため、実写化をスキップし入力画像をそのままスルーパスします。
        """
        outputs = []
        for i, render in enumerate(render_outputs):
            logger.info(f"  [{i+1}/{len(render_outputs)}] {render['scene_id']} - API実写化(FLUX)モックを通過")
            outputs.append({
                "scene_id": render["scene_id"],
                "image": render["rgb"],
            })
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

    async def _upload_file_to_public_url(self, local_path: str) -> str:
        """
        ローカルの画像や音声ファイルを外部API(Kling/Hedra等)へ渡すための公開URLへアップロードする。
        現在は一時的なファイルホスティングとして catbox.moe を使用。
        """
        logger.info(f"  [API準備] ローカルファイルを公開URLへアップロード中...: {local_path}")
        
        import httpx
        url = 'https://catbox.moe/user/api.php'
        
        with open(local_path, 'rb') as f:
            files = {'fileToUpload': (Path(local_path).name, f)}
            data = {'reqtype': 'fileupload'}
            
            async with httpx.AsyncClient() as client:
                try:
                    resp = await client.post(url, data=data, files=files, timeout=60.0)
                    resp.raise_for_status()
                    public_url = resp.text.strip()
                    if not public_url.startswith("http"):
                        raise ValueError(f"予期しないレスポンス: {public_url}")
                    logger.info(f"  [API準備] アップロード成功: {public_url}")
                    return public_url
                except Exception as e:
                    logger.error(f"ファイルアップロードに失敗しました: {e}")
                    raise

    async def _stage_video(self, job_spec: JobSpec, scene_results: List[dict]) -> List[dict]:
        """
        [ハイブリッド移行] Kling AI API による映像生成 + 商用LipSync
        """
        from src.modules.video_gen.kling import KlingAPIClient
        from src.modules.lipsync.sync_so import LipSyncAPIClient
        try:
            kling_client = KlingAPIClient()
        except ValueError as e:
            logger.warning(f"  ⚠ Kling APIキーが未設定です。ダミーにフォールバックします: {e}")
            kling_client = None

        try:
            lipsync_client = LipSyncAPIClient()
        except ValueError as e:
            logger.warning(f"  ⚠ LipSync APIキーが未設定です。LipSync処理プロセスをスキップします: {e}")
            lipsync_client = None

        outputs = []

        for i, res in enumerate(scene_results):
            img = res.get("image")
            audio = res.get("audio")
            if not img:
                continue

            scene_id = res["scene_id"]
            logger.info(f"  [{i+1}/{len(scene_results)}] {scene_id} の動画・音声合成生成 (商用API)")

            video_dir = self.work_dir / f"scene_{i:03d}" / "video"
            video_dir.mkdir(parents=True, exist_ok=True)
            
            video_path = str(video_dir / "clip.mp4")

            duration = res.get("duration", 5.0)
            scene_spec = next((s for s in job_spec.scenes if s.scene_id == scene_id), None)
            kling_prompt = scene_spec.background_prompt if scene_spec and scene_spec.background_prompt else "slow camera pan, subtle natural breathing, realistic movement, highly detailed, cinematic"

            try:
                if kling_client:
                    # 1. 画像の公開URL化
                    public_img_url = await self._upload_file_to_public_url(img)
                    
                    # 2. Kling AI API I2V送信
                    kling_task_id = await kling_client.submit_i2v_task(
                        image_url=public_img_url,
                        prompt=kling_prompt,
                        duration=int(min(5, max(3, duration)))
                    )
                    
                    # 3. Kling AI 動画完成URL取得
                    final_video_url = await kling_client.wait_for_task(kling_task_id, poll_interval_sec=10, timeout_sec=900)
                    
                    # 4. LipSync API に即座にパス（KlingのURLをそのまま流用）
                    if lipsync_client and audio and Path(audio).exists():
                        logger.info(f"  [API中継] Kling動画完了を検知。そのままLipSync APIへ動画URLと音声をパスします。")
                        public_audio_url = await self._upload_file_to_public_url(audio)
                        ls_task_id = await lipsync_client.submit_lipsync_task(final_video_url, public_audio_url)
                        final_video_url = await lipsync_client.wait_for_task(ls_task_id, poll_interval_sec=10, timeout_sec=900)

                    # 5. 完成した100%最終動画のみをローカルにダウンロード
                    import httpx
                    local_video_path = str(video_dir / f"hybrid_final_{scene_id}.mp4")
                    logger.info(f"  [API完了] 最終合成映像をダウンロード中... -> {local_video_path}")
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(final_video_url)
                        with open(local_video_path, "wb") as f:
                            f.write(resp.content)
                            
                    video_path = local_video_path
                else:
                    logger.info(f"  [APIモック] ダミー動画を適用します。")
                    import shutil
                    fallback_candidates = [Path(r"F:\ComfyUI\output\fallback_dummy.mp4")]
                    if fallback_candidates[0].exists():
                        shutil.copy(fallback_candidates[0], video_path)

            except Exception as e:
                logger.error(f"  ❌ 商用API処理エラー ({scene_id}): {e}")
                raise RuntimeError(f"商用API側の処理エラー・タイムアウトが発生しました: {e}")

            outputs.append({
                "scene_id": scene_id,
                "video": video_path,
                "audio": audio,
            })

        logger.info(f"  → {len(outputs)} シーンの商用API動画生成完了")
        return outputs

    async def _stage_compose(self, job: JobSpec, video_outputs: List[dict]) -> Path:
        """
        MoviePy + FFmpeg で全シーンを結合し、BGM・テロップを追加。
        """
        compositor = self._get_compositor()
        output_path = PROJECT_ROOT / job.output_path

        # SRT字幕を生成
        from src.modules.compositor.moviepy_editor.compositor import SubtitleGenerator
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
