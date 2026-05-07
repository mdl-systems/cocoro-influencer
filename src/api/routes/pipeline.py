"""パイプラインAPIルーター (Phase 4)

フルパイプライン実行のAPIエンドポイント。
台本JSON → 音声 → 動画 → 合成を1リクエストで非同期実行する。
単体シーン生成 (POST /scene/generate) も提供。
"""

import json
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models import MessageResponse, PipelineRunRequest, ScriptGenerateRequest
from src.db.schema import JobCRUD, get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

# DBセッション依存性注入型エイリアス
DBSession = Annotated[AsyncSession, Depends(get_session)]


class SceneGenerateRequest(BaseModel):
    """単体シーン生成リクエスト"""

    customer_name: str = "cocoro_customer"   # 顧客名（出力ディレクトリ名に使用）
    scene_index: int = 0                      # ファイル番号 (scene_000_clip.mp4 等)
    text: str                                 # ナレーションテキスト
    pose: str = "neutral"                     # neutral / greeting / walk / fullbody
    camera_angle: str = "upper_body"          # upper_body / full_body / close_up
    cinematic_prompt: str = ""                # 背景・動きプロンプト
    appearance_prompt: str = ""               # 外見プロンプト（Klingに追加）
    scene_type: str = "talking_head"          # "talking_head" | "cinematic" (Wan2.1)


async def _run_full_pipeline(
    job_id: int,
    config_dict: dict,
) -> None:
    """バックグラウンドでフルパイプラインを実行するタスク"""
    from src.db.schema import async_session_factory
    from src.engines.script_engine import ScriptEngine, ScriptScene
    from src.pipeline.orchestrator import Orchestrator, PipelineConfig
    from src.pipeline.orchestrator import ScriptScene as OrchestratorScene

    async with async_session_factory() as session:
        try:
            await JobCRUD.update_status(session, job_id, "running",
                                        progress=0, status_message="パイプライン準備中...")
            await session.commit()

            # ① 字幕: enable_subtitles=True なら caption に scene.text をセット
            scenes = [
                OrchestratorScene(
                    text=s["text"],
                    scene_type=s.get("scene_type", "talking_head"),
                    cinematic_prompt=s.get("cinematic_prompt", ""),
                    caption=s.get("caption", ""),
                    pose=s.get("pose", "neutral"),
                    camera_angle=s.get("camera_angle", "upper_body"),
                    appearance_prompt=s.get("appearance_prompt", ""),
                )
                for s in config_dict["script"]
            ]

            # ② BGMパスを解決
            bgm_path = None
            if config_dict.get("bgm_name"):
                candidate = Path("/data/bgm") / config_dict["bgm_name"]
                if candidate.exists():
                    bgm_path = candidate
                    logger.info("② BGM使用: %s", bgm_path)
                else:
                    logger.warning("② BGMファイルが見つかりません: %s", candidate)

            # B-3 ウォーターマークパスを解決
            watermark_path = None
            if config_dict.get("watermark_name"):
                candidate = Path("/data/logos") / config_dict["watermark_name"]
                if candidate.exists():
                    watermark_path = candidate
                    logger.info("B-3 ウォーターマーク使用: %s", watermark_path)
                else:
                    logger.warning("B-3 ロゴファイルが見つかりません: %s", candidate)

            # avatar_name が指定されている場合、就存のアバター画像を出力ディレクトリにコピー
            avatar_name = config_dict.get("avatar_name", "")
            if avatar_name:
                src_avatar = Path("/data/outputs") / avatar_name / "avatar.png"
                dst_avatar = Path(config_dict["output_dir"]) / "avatar.png"
                if src_avatar.exists() and not dst_avatar.exists():
                    Path(config_dict["output_dir"]).mkdir(parents=True, exist_ok=True)
                    import shutil as _shutil_av
                    _shutil_av.copy2(str(src_avatar), str(dst_avatar))
                    logger.info("avatar_name '%s' からアバターをコピー: %s -> %s", avatar_name, src_avatar, dst_avatar)

            pipeline_config = PipelineConfig(
                scenes=scenes,
                avatar_prompt=config_dict.get("avatar_prompt", ""),
                output_dir=Path(config_dict["output_dir"]),
                lora_path=Path(config_dict["lora_path"]) if config_dict.get("lora_path") else None,
                output_format=config_dict.get("output_format", "shorts"),
                bgm_path=bgm_path,
                bgm_volume=float(config_dict.get("bgm_volume", 0.12)),
                enable_subtitles=bool(config_dict.get("enable_subtitles", False)),
                model_id=int(config_dict.get("model_id", 0)),
                speaker_id=int(config_dict.get("speaker_id", 0)),
                # B-2
                transition=config_dict.get("transition", "none"),
                transition_duration=float(config_dict.get("transition_duration", 0.5)),
                # B-3
                watermark_path=watermark_path,
                watermark_position=config_dict.get("watermark_position", "bottom-right"),
                watermark_scale=float(config_dict.get("watermark_scale", 0.15)),
                # 話速
                speech_speed=float(config_dict.get("speech_speed", 0.50)),
                # エンジン選択
                use_wan22=bool(config_dict.get("use_wan22", False)),
                wan22_guide_scale=float(config_dict.get("wan22_guide_scale", 7.5)),
                use_sadtalker=bool(config_dict.get("use_sadtalker", True)),
                use_liveportrait=bool(config_dict.get("use_liveportrait", False)),
                use_hunyuan_i2v=bool(config_dict.get("use_hunyuan_i2v", False)),
                hunyuan_guidance=float(config_dict.get("hunyuan_guidance", 9.0)),
                hunyuan_steps=int(config_dict.get("hunyuan_steps", 30)),
                use_musetalk=bool(config_dict.get("use_musetalk", False)),
                musetalk_batch_size=int(config_dict.get("musetalk_batch_size", 8)),
            )

            # 進捗コールバック: Orchestratorの各ステップでDBを更新
            from src.db.schema import async_session_factory as _sf

            async def on_progress(pct: int, msg: str) -> None:
                async with _sf() as _sess:
                    await JobCRUD.update_status(
                        _sess, job_id, "running",
                        progress=pct, status_message=msg,
                    )
                    await _sess.commit()

            orchestrator = Orchestrator(pipeline_config)
            final_path = await orchestrator.run(on_progress=on_progress)

            # ✅ 完了後: /data/outputs/videos/ にタイムスタンプ付きでアーカイブ
            import shutil as _shutil
            from datetime import datetime as _dt
            videos_dir = Path("/data/outputs/videos")
            videos_dir.mkdir(parents=True, exist_ok=True)
            ts = _dt.now().strftime("%Y%m%d_%H%M%S")
            safe_name_arc = config_dict.get("customer_name", "video").replace(" ", "_").replace("/", "_")
            archive_name = f"{safe_name_arc}_{ts}.mp4"
            archive_path = videos_dir / archive_name
            _shutil.copy2(str(final_path), str(archive_path))
            logger.info("アーカイブ完了: %s", archive_path)

            await JobCRUD.update_status(
                session, job_id, "done", output_path=str(final_path),
                progress=100, status_message=f"完了 | アーカイブ: {archive_name}",
            )
            await session.commit()
            logger.info("フルパイプライン完了: job_id=%d, output=%s", job_id, final_path)

        except Exception as e:
            logger.exception("フルパイプラインエラー: job_id=%d", job_id)
            await JobCRUD.update_status(session, job_id, "error", error_message=str(e))
            await session.commit()



@router.post("/run", response_model=MessageResponse, status_code=202)
async def run_pipeline(
    request: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    session: DBSession,
) -> MessageResponse:
    """フルパイプラインを非同期実行する

    台本設定を受け取り、以下を順番にバックグラウンドで実行する:
    1. アバター画像生成 (FLUX.1-dev)
    2. 各シーンの音声合成 (Style-Bert-VITS2)
    3. 各シーンの動画生成 (Wan2.1 I2V + Wav2Lip リップシンク)
    4. FFmpegで最終動画合成

    202 Accepted を即座に返し、job_idでステータスをポーリング可能。
    """
    # 出力ディレクトリ
    safe_name = request.customer_name.replace(" ", "_").replace("/", "_")
    output_dir = Path("/data/outputs") / safe_name

    # ジョブ作成
    params = json.dumps({
        "customer_name": request.customer_name,
        "avatar_prompt": request.avatar_prompt,
        "output_format": request.output_format,
        "scene_count": len(request.script),
    }, ensure_ascii=False)
    job = await JobCRUD.create(session, job_type="pipeline", params=params)
    # バックグラウンドタスク起動前に明示的コミット
    # (FastAPIのBGタスクはDep cleanupより先に走るため、flush()だけでは見えない)
    await session.commit()

    # バックグラウンドタスク登録
    config_dict = {
        "script": request.script,
        "avatar_prompt": request.avatar_prompt,
        "avatar_name": request.avatar_name,
        "output_dir": str(output_dir),
        "customer_name": request.customer_name,
        "lora_path": request.lora_path,
        "output_format": request.output_format,
        # ① 字幕
        "enable_subtitles": request.enable_subtitles,
        # ② BGM
        "bgm_name": request.bgm_name,
        "bgm_volume": request.bgm_volume,
        # ③ 音声
        "model_id": request.model_id,
        "speaker_id": request.speaker_id,
        # B-2 トランジション
        "transition": request.transition,
        "transition_duration": request.transition_duration,
        # B-3 ウォーターマーク
        "watermark_name": request.watermark_name,
        "watermark_position": request.watermark_position,
        "watermark_scale": request.watermark_scale,
        # ④ 話速
        "speech_speed": request.speech_speed,
        # ⑤ 動画エンジン選択
        "use_wan22": request.use_wan22,
        "wan22_guide_scale": request.wan22_guide_scale,
        "use_liveportrait": request.use_liveportrait,
        "use_sadtalker": request.use_sadtalker,
        "use_musetalk": request.use_musetalk,
        "musetalk_batch_size": request.musetalk_batch_size,
        "use_hunyuan_i2v": request.use_hunyuan_i2v,
        "hunyuan_guidance": request.hunyuan_guidance,
        "hunyuan_steps": request.hunyuan_steps,
    }
    background_tasks.add_task(_run_full_pipeline, job_id=job.id, config_dict=config_dict)

    return MessageResponse(
        message=f"パイプラインジョブを開始しました ({len(request.script)}シーン)",
        job_id=job.id,
    )


async def _run_single_scene_task(job_id: int, config_dict: dict) -> None:
    """バックグラウンドで単体シーン生成を実行するタスク"""
    from src.db.schema import async_session_factory
    from src.pipeline.orchestrator import Orchestrator, PipelineConfig, ScriptScene

    async with async_session_factory() as session:
        try:
            await JobCRUD.update_status(session, job_id, "running")
            await session.commit()

            scene = ScriptScene(
                text=config_dict["text"],
                scene_type=config_dict.get("scene_type", "talking_head"),
                pose=config_dict.get("pose", "neutral"),
                camera_angle=config_dict.get("camera_angle", "upper_body"),
                cinematic_prompt=config_dict.get("cinematic_prompt", ""),
                appearance_prompt=config_dict.get("appearance_prompt", ""),
            )
            pipeline_config = PipelineConfig(
                scenes=[scene],
                avatar_prompt="",
                output_dir=Path(config_dict["output_dir"]),
            )
            orchestrator = Orchestrator(pipeline_config)

            # 進捗コールバック: 単体シーン生成中もDBを更新
            from src.db.schema import async_session_factory as _sf

            async def on_progress(pct: int, msg: str) -> None:
                async with _sf() as _sess:
                    await JobCRUD.update_status(
                        _sess, job_id, "running",
                        progress=pct, status_message=msg,
                    )
                    await _sess.commit()

            clip_path = await orchestrator.run_single_scene(
                scene=scene,
                scene_index=config_dict.get("scene_index", 0),
                on_progress=on_progress,
            )

            await JobCRUD.update_status(session, job_id, "done", output_path=str(clip_path))
            await session.commit()
            logger.info("単体シーン生成完了: job_id=%d clip=%s", job_id, clip_path)

        except Exception as exc:
            logger.exception("単体シーン生成エラー: job_id=%d", job_id)
            await JobCRUD.update_status(session, job_id, "error", error_message=str(exc))
            await session.commit()


@router.post("/scene/generate", response_model=MessageResponse, status_code=202)
async def generate_scene(
    request: SceneGenerateRequest,
    background_tasks: BackgroundTasks,
    session: DBSession,
) -> MessageResponse:
    """1シーンのみ動画生成（8秒単体生成モード）

    アバター生成をスキップし、音声→Kling AI→Wav2Lipのみ実行する。
    全体パイプライン (/run) より高速に1クリップを生成できる。

    Returns:
        202 Accepted + job_id (ポーリング: GET /api/v1/jobs/{job_id})
    """
    safe_name = request.customer_name.replace(" ", "_").replace("/", "_")
    output_dir = Path("/data/outputs") / safe_name

    params = json.dumps({
        "customer_name": request.customer_name,
        "scene_index": request.scene_index,
        "text": request.text[:50] + "...",
        "pose": request.pose,
        "camera_angle": request.camera_angle,
    }, ensure_ascii=False)
    job = await JobCRUD.create(session, job_type="scene_generate", params=params)
    # バックグラウンドタスク起動前に明示的コミット
    await session.commit()

    config_dict = {
        "text": request.text,
        "pose": request.pose,
        "camera_angle": request.camera_angle,
        "cinematic_prompt": request.cinematic_prompt,
        "appearance_prompt": request.appearance_prompt,
        "scene_index": request.scene_index,
        "scene_type": request.scene_type,
        "output_dir": str(output_dir),
    }
    background_tasks.add_task(_run_single_scene_task, job_id=job.id, config_dict=config_dict)

    return MessageResponse(
        message=f"単体シーン生成を開始しました (scene_{request.scene_index:03d})",
        job_id=job.id,
    )


@router.get("/bgm/list", response_model=dict)
async def list_bgm() -> dict:
    """/data/bgm/ にあるBGMファイル一覧を返す

    ファイルをサーバーの /data/bgm/ に置き、このエンドポイントで取得できる。
    """
    bgm_dir = Path("/data/bgm")
    if not bgm_dir.exists():
        return {"files": []}
    files = sorted(
        f.name for f in bgm_dir.iterdir()
        if f.suffix.lower() in (".mp3", ".wav", ".m4a", ".aac", ".ogg")
    )
    return {"files": files}


@router.get("/voices", response_model=dict)
async def list_voices() -> dict:
    """利用可能なStyle-Bert-VITS2モデル一覧を返す"""
    import requests as _req
    try:
        resp = _req.get("http://localhost:5000/models/info", timeout=5)
        resp.raise_for_status()
        return {"models": resp.json()}
    except Exception as e:
        logger.warning("VITS2 models/info 取得失敗: %s", e)
        return {"models": []}


@router.get("/logos/list", response_model=dict)
async def list_logos() -> dict:
    """/data/logos/ にあるロゴファイル一覧を返す (B-3)"""
    logos_dir = Path("/data/logos")
    if not logos_dir.exists():
        return {"logos": []}
    logos = sorted(
        f.name for f in logos_dir.iterdir()
        if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
    )
    return {"logos": logos}


@router.post("/logos/upload", response_model=dict)
async def upload_logo(file: UploadFile = File(...)) -> dict:
    """ロゴ画像をアップロードし /data/logos/ に保存する (B-3)"""
    import shutil as _sh
    logos_dir = Path("/data/logos")
    logos_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "logo.png").name
    dest = logos_dir / safe_name
    with dest.open("wb") as f:
        _sh.copyfileobj(file.file, f)
    logger.info("B-3 ロゴアップロード: %s (%d bytes)", safe_name, dest.stat().st_size)
    return {"filename": safe_name, "path": str(dest)}



@router.post("/script/generate", response_model=dict, status_code=200)
async def generate_script(
    request: ScriptGenerateRequest,
) -> dict:
    """LLMで台本を自動生成する

    Ollama (ローカル) または外部LLMプロバイダーを使って、
    企業紹介動画の台本を自動生成する。

    provider オプション:
    - ollama    : ローカルOllama — APIキー不要 (デフォルト)
    - openai    : cocoro-llm-server (192.168.50.112:8000)
    - gemini    : Google Gemini API (GEMINI_API_KEY 必要)
    - anthropic : Anthropic Claude  (ANTHROPIC_API_KEY 必要)

    Returns:
        生成された台本 (ScriptEngineの出力JSON形式)
    """
    from src.engines.script_engine import ScriptEngine

    try:
        engine = ScriptEngine(provider=request.provider)
        engine.load()
        output_dir = Path("/data/outputs") / request.company_name.replace(" ", "_")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "script.json"

        script = engine.generate(
            company_name=request.company_name,
            product_name=request.product_name,
            target_audience=request.target_audience,
            tone=request.tone,
            duration=request.duration,
            output_path=output_path,
        )
        result = ScriptEngine._script_to_dict(script)
        logger.info(
            "台本生成完了: company=%s, provider=%s, scenes=%d",
            request.company_name,
            request.provider,
            len(result.get("scenes", [])),
        )
        return result
    except RuntimeError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e)) from e

