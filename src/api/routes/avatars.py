"""アバター生成APIルーター

アバター画像の生成・一覧取得・詳細取得を提供する。
生成はバックグラウンドタスクで非同期実行する。
"""

import json
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models import AvatarGenerateRequest, AvatarListResponse, AvatarResponse, MessageResponse
from src.db.schema import AvatarCRUD, JobCRUD, get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/avatars", tags=["avatars"])

# DBセッション依存性注入型エイリアス
DBSession = Annotated[AsyncSession, Depends(get_session)]


async def _run_avatar_generation(
    job_id: int,
    customer_name: str,
    prompt: str,
    output_path: Path,
    lora_path: Path | None,
    width: int,
    height: int,
    num_inference_steps: int,
    seed: int | None,
) -> None:
    """バックグラウンドでアバター画像を生成するタスク"""
    from src.engines.flux_engine import FluxEngine
    from src.engines.manager import EngineManager
    from src.db.schema import async_session_factory

    async with async_session_factory() as session:
        try:
            # ステータスをrunningに更新
            await JobCRUD.update_status(session, job_id, "running")
            await session.commit()

            # FluxEngineで生成
            manager = EngineManager()
            engine = FluxEngine()
            manager.register("flux", engine)
            result_engine = manager.get("flux")

            result_path = result_engine.generate(
                prompt=prompt,
                output_path=output_path,
                lora_path=lora_path,
                width=width,
                height=height,
                num_inference_steps=num_inference_steps,
                seed=seed,
            )

            # アバターレコードを作成
            await AvatarCRUD.create(
                session,
                customer_name=customer_name,
                prompt=prompt,
                image_path=str(result_path),
                lora_path=str(lora_path) if lora_path else None,
                job_id=job_id,
            )

            # ステータスをdoneに更新
            await JobCRUD.update_status(session, job_id, "done", output_path=str(result_path))
            await session.commit()
            logger.info("アバター生成完了: job_id=%d", job_id)

        except Exception as e:
            logger.exception("アバター生成エラー: job_id=%d", job_id)
            await JobCRUD.update_status(session, job_id, "error", error_message=str(e))
            await session.commit()


@router.post("/generate", response_model=MessageResponse, status_code=202)
async def generate_avatar(
    request: AvatarGenerateRequest,
    background_tasks: BackgroundTasks,
    session: DBSession,
) -> MessageResponse:
    """アバター画像生成を開始する (非同期実行)

    ジョブを作成して即座にjob_idを返す。
    実際の生成はバックグラウンドで実行される。
    """
    # 出力パスを決定
    output_dir = Path("outputs") / request.customer_name.replace(" ", "_")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "avatar.png"

    # ジョブを作成
    params = json.dumps({
        "customer_name": request.customer_name,
        "prompt": request.prompt,
        "width": request.width,
        "height": request.height,
        "num_inference_steps": request.num_inference_steps,
        "seed": request.seed,
    }, ensure_ascii=False)
    job = await JobCRUD.create(session, job_type="avatar", params=params)

    # バックグラウンドタスク登録
    background_tasks.add_task(
        _run_avatar_generation,
        job_id=job.id,
        customer_name=request.customer_name,
        prompt=request.prompt,
        output_path=output_path,
        lora_path=Path(request.lora_path) if request.lora_path else None,
        width=request.width,
        height=request.height,
        num_inference_steps=request.num_inference_steps,
        seed=request.seed,
    )

    return MessageResponse(message="アバター生成ジョブを開始しました", job_id=job.id)


@router.get("/", response_model=AvatarListResponse)
async def list_avatars(session: DBSession) -> AvatarListResponse:
    """アバター一覧を取得する"""
    avatars = await AvatarCRUD.list_all(session)
    return AvatarListResponse(avatars=avatars, total=len(avatars))


@router.get("/{avatar_id}", response_model=AvatarResponse)
async def get_avatar(avatar_id: int, session: DBSession) -> AvatarResponse:
    """アバター詳細を取得する"""
    avatar = await AvatarCRUD.get_by_id(session, avatar_id)
    if avatar is None:
        raise HTTPException(status_code=404, detail=f"アバターが見つかりません: id={avatar_id}")
    return avatar


async def _run_instantid_generation(job_id: int, customer_name: str) -> None:
    """バックグラウンドでInstantIDポーズ別画像生成を実行するタスク"""
    import subprocess
    from src.db.schema import async_session_factory

    async with async_session_factory() as session:
        try:
            await JobCRUD.update_status(session, job_id, "running")
            await session.commit()

            # InstantID スクリプトを venv python で実行
            venv_python = "/mnt/models/InstantID/venv/bin/python"
            script_path = "/home/cocoro-influencer/scripts/generate_instantid_poses.py"

            logger.info("InstantID 生成開始: customer=%s", customer_name)
            result = subprocess.run(
                [venv_python, script_path, "--customer_name", customer_name],
                capture_output=True,
                text=True,
                timeout=3600,   # 最大1時間
                cwd="/mnt/models/InstantID",
            )

            if result.stdout:
                logger.info("InstantID stdout:\n%s", result.stdout[-2000:])
            if result.returncode != 0:
                error_msg = result.stderr[-1000:] if result.stderr else "不明なエラー"
                raise RuntimeError(f"InstantID生成エラー: {error_msg}")

            output_dir = f"/mnt/data/outputs/{customer_name}"
            await JobCRUD.update_status(session, job_id, "done", output_path=output_dir)
            await session.commit()
            logger.info("InstantID 生成完了: customer=%s", customer_name)

        except Exception as exc:
            logger.exception("InstantID 生成エラー: job_id=%d", job_id)
            await JobCRUD.update_status(session, job_id, "error", error_message=str(exc))
            await session.commit()


@router.post("/upload", response_model=MessageResponse, status_code=200)
async def upload_avatar(
    customer_name: str,
    file: "UploadFile",
    session: DBSession,
    background_tasks: BackgroundTasks,
    fullbody_file: "UploadFile | None" = None,
) -> MessageResponse:
    """アバター画像をアップロードして保存し、InstantIDポーズ生成をキックオフする

    Returns:
        job_id: InstantID生成ジョブID (GET /api/v1/jobs/{job_id} でポーリング可能)
        status: done になったら 4種のポーズ画像がサーバーに生成済み
    """
    from fastapi import UploadFile
    import shutil

    output_dir = Path("/mnt/data/outputs") / customer_name.replace(" ", "_")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 顔写真保存
    output_path = output_dir / "avatar.png"
    with open(output_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    logger.info("顔写真アップロード完了: %s", output_path)

    has_fullbody = False
    # 全身写真保存（任意）
    if fullbody_file is not None:
        fullbody_path = output_dir / "avatar_fullbody_ref.png"
        with open(fullbody_path, "wb") as f:
            shutil.copyfileobj(fullbody_file.file, f)
        logger.info("全身写真アップロード完了: %s", fullbody_path)
        has_fullbody = True

    # InstantID ポーズ生成ジョブを作成してバックグラウンドで起動
    import json
    params = json.dumps({
        "customer_name": customer_name,
        "has_fullbody": has_fullbody,
    }, ensure_ascii=False)
    job = await JobCRUD.create(session, job_type="instantid", params=params)
    background_tasks.add_task(_run_instantid_generation, job_id=job.id, customer_name=customer_name)

    msg = (
        f"{'顔写真・全身写真' if has_fullbody else '顔写真'}を保存しました。"
        f"InstantIDポーズ生成を開始しました（約10〜20分）"
    )
    return MessageResponse(message=msg, job_id=job.id)

