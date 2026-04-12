"""FastAPIメインアプリケーション

cocoro-influencer REST API。
アバター生成・音声合成・ジョブ管理のAPIを提供する。

起動方法:
    uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8080 --reload
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.routes import avatars, jobs, pipeline
from src.db.schema import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """アプリ起動/終了時の処理"""
    # 起動時: DB初期化
    logger.info("cocoro-influencer API 起動中...")
    await init_db()
    logger.info("API起動完了 → http://localhost:8080")
    logger.info("APIドキュメント → http://localhost:8080/docs")
    yield
    # 終了時の処理 (必要なら追加)
    logger.info("cocoro-influencer API 終了")


# FastAPIアプリ定義
app = FastAPI(
    title="cocoro-influencer API",
    description="企業専属AIインフルエンサー生成システム REST API",
    version="0.3.0",
    lifespan=lifespan,
)

# CORS設定 (Next.jsフロントエンドからのアクセスを許可)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # Next.js 開発サーバー
        "http://localhost:8080",   # 同一オリジン
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ルーター登録
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(avatars.router, prefix="/api/v1")
app.include_router(pipeline.router, prefix="/api/v1")

# 静的ファイル配信 (生成物)
outputs_dir = Path("outputs")
outputs_dir.mkdir(exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")


@app.get("/")
async def root() -> dict:
    """ヘルスチェックエンドポイント"""
    return {
        "service": "cocoro-influencer API",
        "version": "0.3.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health() -> dict:
    """ヘルスチェック"""
    return {"status": "ok"}

# Static files for Web UI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app.mount("/ui", StaticFiles(directory="/home/cocoro-influencer/ui"), name="ui")

@app.get("/studio")
async def studio():
    return FileResponse("/home/cocoro-influencer/ui/index.html")

@app.get("/studio")
async def studio():
    from fastapi.responses import FileResponse
    return FileResponse("/home/cocoro-influencer/ui/index.html")

app.mount("/static", StaticFiles(directory="/home/cocoro-influencer/static"), name="static")
