"""パイプラインAPIルーター (Phase 4)

フルパイプライン実行のAPIエンドポイント。
台本JSON → 音声 → 動画 → 合成を1リクエストで非同期実行する。
単体シーン生成 (POST /scene/generate) も提供。
"""

import json
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models import MessageResponse, PipelineRunRequest
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

            # 台本シーンをOrchestratorのSceneに変換
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

            pipeline_config = PipelineConfig(
                scenes=scenes,
                avatar_prompt=config_dict["avatar_prompt"],
                output_dir=Path(config_dict["output_dir"]),
                lora_path=Path(config_dict["lora_path"]) if config_dict.get("lora_path") else None,
                output_format=config_dict.get("output_format", "shorts"),
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

            await JobCRUD.update_status(
                session, job_id, "done", output_path=str(final_path),
                progress=100, status_message="完了",
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
    1. アバター画像生成 (FLUX.2)
    2. 各シーンの音声合成 (VOICEVOX)
    3. 各シーンの動画生成 (EchoMimic / Wan 2.6)
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
        "output_dir": str(output_dir),
        "lora_path": request.lora_path,
        "output_format": request.output_format,
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
            clip_path = await orchestrator.run_single_scene(
                scene=scene,
                scene_index=config_dict.get("scene_index", 0),
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


@router.post("/script/generate", response_model=dict, status_code=200)
async def generate_script_api(
    company_name: str,
    product_name: str,
    target_audience: str = "20代〜40代のビジネスパーソン",
    tone: str = "プロフェッショナルで親しみやすい",
    duration: str = "60秒",
    provider: str = "ollama",
) -> dict:
    """LLMで台本を生成してJSONを返す

    provider (デフォルト: ollama):
    - ollama    : ローカルOllama — APIキー不要 (デフォルト)
    - openai    : cocoro-llm-server (192.168.50.112:8000)
    - gemini    : Google Gemini API (GEMINI_API_KEY 必要)
    - anthropic : Anthropic Claude  (ANTHROPIC_API_KEY 必要)
    """
    from src.engines.script_engine import ScriptEngine

    try:
        engine = ScriptEngine(provider=provider)
        engine.load()
        output_dir = Path("outputs") / company_name.replace(" ", "_")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "script.json"

        script = engine.generate(
            company_name=company_name,
            product_name=product_name,
            target_audience=target_audience,
            tone=tone,
            duration=duration,
            output_path=output_path,
        )
        return ScriptEngine._script_to_dict(script)
    except RuntimeError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e)) from e
