"""ビデオライブラリAPIルーター

/data/outputs/ 以下の生成済みMP4ファイルを一覧・管理するAPI。
Veo3風のギャラリーUIからポーリングなしで動画を閲覧できる。
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/videos", tags=["videos"], redirect_slashes=False)

# 本番サーバーの出力ディレクトリ
OUTPUTS_DIR = Path("/data/outputs")


class VideoItem(BaseModel):
    """生成済み動画のメタデータ"""
    id: str                        # outputs相対パス (customer/filename.mp4)
    url: str                       # ブラウザからアクセス可能なURL
    filename: str                  # ファイル名
    customer_name: str             # 顧客名 (サブディレクトリ名)
    size_bytes: int                # ファイルサイズ
    duration_hint: Optional[float] # 動画長（将来拡張用、現在はNone）
    created_at: str                # ISO 8601 作成日時
    is_final: bool                 # final_ プレフィックスで最終合成かどうか


class VideoListResponse(BaseModel):
    """動画一覧レスポンス"""
    videos: list[VideoItem]
    total: int


def _scan_videos(outputs_dir: Path, customer_filter: Optional[str] = None) -> list[VideoItem]:
    """outputs/以下のMP4を再帰スキャンしてリスト返却"""
    items: list[VideoItem] = []

    if not outputs_dir.exists():
        return items

    try:
        # 顧客ディレクトリを列挙
        for customer_dir in sorted(outputs_dir.iterdir()):
            if not customer_dir.is_dir():
                continue

            customer_name = customer_dir.name

            # 顧客フィルター
            if customer_filter and customer_name != customer_filter:
                continue

            # そのディレクトリ以下のMP4を再帰スキャン
            for mp4_path in sorted(customer_dir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    stat = mp4_path.stat()
                    rel_path = mp4_path.relative_to(outputs_dir)
                    video_id = rel_path.as_posix()  # customer_name/filename.mp4

                    items.append(VideoItem(
                        id=video_id,
                        url=f"/outputs/{video_id}",
                        filename=mp4_path.name,
                        customer_name=customer_name,
                        size_bytes=stat.st_size,
                        duration_hint=None,
                        created_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        is_final=mp4_path.name.startswith("final_"),
                    ))
                except Exception as e:
                    logger.warning("ファイルスキャンエラー: %s — %s", mp4_path, e)

    except Exception as e:
        logger.error("outputs ディレクトリスキャンエラー: %s", e)

    return items


@router.get("/", response_model=VideoListResponse)
async def list_videos(
    customer: Optional[str] = Query(None, description="顧客名でフィルター"),
    final_only: bool = Query(False, description="最終合成動画のみ表示"),
    limit: int = Query(100, ge=1, le=500, description="最大取得件数"),
    offset: int = Query(0, ge=0, description="オフセット"),
) -> VideoListResponse:
    """生成済み動画の一覧を返す

    /data/outputs/ 以下のMP4を再帰スキャンして返却する。
    更新日時の降順 (最新が先頭) でソート済み。
    """
    videos = _scan_videos(OUTPUTS_DIR, customer_filter=customer)

    # 最終合成のみフィルター
    if final_only:
        videos = [v for v in videos if v.is_final]

    total = len(videos)
    videos = videos[offset: offset + limit]

    return VideoListResponse(videos=videos, total=total)


@router.get("/customers", response_model=list[str])
async def list_customers() -> list[str]:
    """顧客名（=outputs以下のサブディレクトリ名）の一覧を返す"""
    if not OUTPUTS_DIR.exists():
        return []
    try:
        return sorted(
            d.name for d in OUTPUTS_DIR.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
    except Exception as e:
        logger.error("顧客ディレクトリ一覧取得エラー: %s", e)
        return []


@router.delete("/{video_id:path}", status_code=204)
async def delete_video(video_id: str) -> None:
    """指定した動画ファイルを削除する

    video_idはURLエンコードされたoutputs相対パス (customer/filename.mp4)。
    パストラバーサル攻撃を防ぐため /data/outputs/ 配下のみ許可。
    """
    # パストラバーサル防止: outputs_dir 配下のみ
    target = (OUTPUTS_DIR / video_id).resolve()
    if not str(target).startswith(str(OUTPUTS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="不正なパスです")

    if not target.exists():
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")

    if target.suffix.lower() != ".mp4":
        raise HTTPException(status_code=400, detail="MP4ファイルのみ削除可能です")

    try:
        target.unlink()
        logger.info("動画削除: %s", target)
    except Exception as e:
        logger.error("動画削除エラー: %s — %s", target, e)
        raise HTTPException(status_code=500, detail=f"削除失敗: {e}") from e
