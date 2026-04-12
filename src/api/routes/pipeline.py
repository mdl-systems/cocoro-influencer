"""パイプラインAPIルーター (Phase 4)

フルパイプライン実行のAPIエンドポイント。
台本JSON → 音声 → 動画 → 合成を1リクエストで非同期実行する。
"""

import json
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models import MessageResponse, PipelineRunRequest
from src.db.schema import JobCRUD, get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

# DBセッション依存性注入型エイリアス
DBSession = Annotated[AsyncSession, Depends(get_session)]


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
            await JobCRUD.update_status(session, job_id, "running")
            await session.commit()

            # 台本シーンをOrchestratorのSceneに変換
            scenes = [
                OrchestratorScene(
                    text=s["text"],
                    scene_type=s.get("scene_type", "talking_head"),
                    cinematic_prompt=s.get("cinematic_prompt", ""),
                    caption=s.get("caption", ""),
                    pose=s.get("pose", "neutral"),
                    appearance_prompt=s.get("appearance_prompt", ""),
                )
                for s in config_dict["script"]
            ]

            pipeline_config = PipelineConfig(
                scenes=scenes,
                avatar_prompt=config_dict["avatar_prompt"],
                output_dir=Path(config_dict["output_dir"]),
                lora_path=Path(config_dict["lora_path"]) if config_dict.get("lora_path") else None,
                output_format=config_dict.get("output_format", "youtube"),
            )

            orchestrator = Orchestrator(pipeline_config)
            final_path = await orchestrator.run()

            await JobCRUD.update_status(
                session, job_id, "done", output_path=str(final_path)
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
    output_dir = Path("/mnt/data/outputs") / safe_name

    # ジョブ作成
    params = json.dumps({
        "customer_name": request.customer_name,
        "avatar_prompt": request.avatar_prompt,
        "output_format": request.output_format,
        "scene_count": len(request.script),
    }, ensure_ascii=False)
    job = await JobCRUD.create(session, job_type="pipeline", params=params)

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
