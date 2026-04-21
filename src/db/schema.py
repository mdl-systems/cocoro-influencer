"""DBスキーマ定義とCRUD操作

SQLAlchemy + aiosqliteを使用した非同期DB操作。
Phase 3ではSQLiteを使用、Phase 3以降でPostgreSQLに移行可能。
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import Column, DateTime, Integer, String, Text, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)

# DBファイルパス
DB_PATH = Path(__file__).parent.parent.parent / "outputs" / "cocoro.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

# 非同期エンジン作成
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # SQL ログ出力 (開発時はTrue)
)

# セッションファクトリ
async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy ORMベースクラス"""
    pass


class Job(Base):
    """ジョブ履歴テーブル

    AIインフルエンサー生成の各ジョブを記録する。
    """

    __tablename__ = "jobs"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    # ジョブ種別: "avatar" | "voice" | "talking_head" | "cinematic" | "compose" | "pipeline"
    job_type: str = Column(String(32), nullable=False)
    # ステータス: "pending" | "running" | "done" | "error"
    status: str = Column(String(16), nullable=False, default="pending")
    # 入力パラメータ (JSON文字列)
    params: str = Column(Text, nullable=True)
    # 出力ファイルパス
    output_path: str = Column(Text, nullable=True)
    # エラーメッセージ
    error_message: str = Column(Text, nullable=True)
    # タイムスタンプ
    created_at: datetime = Column(DateTime, default=func.now(), nullable=False)
    updated_at: datetime = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    # 進捗 (0-100) とステータスメッセージ (後から追加カラム)
    progress: int = Column(Integer, nullable=True)
    status_message: str = Column(String(256), nullable=True)


class Avatar(Base):
    """アバター管理テーブル

    生成したアバター画像を顧客別に管理する。
    """

    __tablename__ = "avatars"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    # 顧客名
    customer_name: str = Column(String(128), nullable=False)
    # 生成プロンプト
    prompt: str = Column(Text, nullable=False)
    # LoRAパス
    lora_path: str = Column(Text, nullable=True)
    # 画像ファイルパス
    image_path: str = Column(Text, nullable=False)
    # 生成ジョブID
    job_id: int = Column(Integer, nullable=True)
    # タイムスタンプ
    created_at: datetime = Column(DateTime, default=func.now(), nullable=False)


async def init_db() -> None:
    """テーブルを作成する (初回起動時)

    既存DBへの後方互換マイグレーション:
    progress / status_message カラムは ALTER TABLE で追加 (なければ追加、あれば無視)
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # SQLite ALTER TABLE: カラムが存在しない場合のみ追加
    for col_def in [
        "ALTER TABLE jobs ADD COLUMN progress INTEGER",
        "ALTER TABLE jobs ADD COLUMN status_message TEXT",
    ]:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(col_def))
        except Exception:
            pass  # 既に存在する場合は無視

    logger.info("DB初期化完了: %s", DB_PATH)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI依存性注入用のDBセッションジェネレータ"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# --- CRUD操作 ---

class JobCRUD:
    """ジョブのCRUD操作"""

    @staticmethod
    async def create(
        session: AsyncSession,
        job_type: str,
        params: str | None = None,
    ) -> Job:
        """ジョブを作成する"""
        job = Job(job_type=job_type, status="pending", params=params)
        session.add(job)
        await session.flush()
        logger.info("ジョブ作成: id=%d, type=%s", job.id, job_type)
        return job

    @staticmethod
    async def get_by_id(session: AsyncSession, job_id: int) -> Job | None:
        """IDでジョブを取得する"""
        result = await session.execute(select(Job).where(Job.id == job_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(
        session: AsyncSession,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        """ジョブ一覧を取得する (新しい順)"""
        result = await session.execute(
            select(Job).order_by(Job.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    @staticmethod
    async def update_status(
        session: AsyncSession,
        job_id: int,
        status: str,
        output_path: str | None = None,
        error_message: str | None = None,
        progress: int | None = None,
        status_message: str | None = None,
    ) -> Job | None:
        """ジョブのステータス・進捗を更新する"""
        job = await JobCRUD.get_by_id(session, job_id)
        if job is None:
            return None
        job.status = status
        if output_path is not None:
            job.output_path = output_path
        if error_message is not None:
            job.error_message = error_message
        if progress is not None:
            job.progress = progress
        if status_message is not None:
            job.status_message = status_message
        logger.info("ジョブ更新: id=%d, status=%s", job_id, status)
        return job


class AvatarCRUD:
    """アバターのCRUD操作"""

    @staticmethod
    async def create(
        session: AsyncSession,
        customer_name: str,
        prompt: str,
        image_path: str,
        lora_path: str | None = None,
        job_id: int | None = None,
    ) -> Avatar:
        """アバターを作成する"""
        avatar = Avatar(
            customer_name=customer_name,
            prompt=prompt,
            image_path=image_path,
            lora_path=lora_path,
            job_id=job_id,
        )
        session.add(avatar)
        await session.flush()
        return avatar

    @staticmethod
    async def list_all(session: AsyncSession, limit: int = 50) -> list[Avatar]:
        """アバター一覧を取得する (新しい順)"""
        result = await session.execute(
            select(Avatar).order_by(Avatar.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(session: AsyncSession, avatar_id: int) -> Avatar | None:
        """IDでアバターを取得する"""
        result = await session.execute(select(Avatar).where(Avatar.id == avatar_id))
        return result.scalar_one_or_none()
