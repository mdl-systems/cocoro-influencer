"""Pydanticモデル定義 (API リクエスト/レスポンス)

FastAPIのリクエスト/レスポンスで使用するPydanticスキーマ。
ORMモデルとは分離して定義する。
"""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


# =============================================================================
# Job スキーマ
# =============================================================================

class JobCreate(BaseModel):
    """ジョブ作成リクエスト"""

    job_type: str = Field(..., description="ジョブ種別 (avatar/voice/talking_head/cinematic/compose)")
    params: dict = Field(default_factory=dict, description="入力パラメータ")


class JobResponse(BaseModel):
    """ジョブレスポンス"""

    id: int
    job_type: str
    status: str  # pending | running | done | error
    params: str | None
    output_path: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    """ジョブ一覧レスポンス"""

    jobs: list[JobResponse]
    total: int


# =============================================================================
# Avatar スキーマ
# =============================================================================

class AvatarGenerateRequest(BaseModel):
    """アバター生成リクエスト"""

    customer_name: str = Field(..., min_length=1, max_length=128, description="顧客名")
    prompt: str = Field(..., min_length=1, description="画像生成プロンプト")
    lora_path: str | None = Field(None, description="LoRAファイルパス (オプション)")
    width: int = Field(1024, ge=256, le=2048, description="画像幅 (px)")
    height: int = Field(1024, ge=256, le=2048, description="画像高さ (px)")
    num_inference_steps: int = Field(30, ge=1, le=100, description="推論ステップ数")
    seed: int | None = Field(None, description="ランダムシード")


class AvatarResponse(BaseModel):
    """アバターレスポンス"""

    id: int
    customer_name: str
    prompt: str
    lora_path: str | None
    image_path: str
    job_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AvatarListResponse(BaseModel):
    """アバター一覧レスポンス"""

    avatars: list[AvatarResponse]
    total: int


# =============================================================================
# Voice スキーマ
# =============================================================================

class VoiceGenerateRequest(BaseModel):
    """音声合成リクエスト"""

    text: str = Field(..., min_length=1, description="読み上げテキスト")
    speaker_id: int = Field(3, ge=0, description="VOICEVOX 話者ID")
    speed_scale: float = Field(1.0, ge=0.5, le=2.0, description="話速")
    output_filename: str = Field("voice.wav", description="出力ファイル名")


# =============================================================================
# Pipeline スキーマ
# =============================================================================

class PipelineRunRequest(BaseModel):
    """フルパイプライン実行リクエスト"""

    customer_name: str = Field(..., min_length=1, description="顧客名")
    avatar_prompt: str = Field(..., min_length=1, description="アバタープロンプト")
    script: list[dict] = Field(..., min_length=1, description="台本 [{text, scene_type, caption}]")
    lora_path: str | None = Field(None, description="LoRAパス")
    output_format: str = Field("youtube", description="出力フォーマット")
    avatar_seed: int | None = Field(None, description="アバター生成シード")


# =============================================================================
# 共通レスポンス
# =============================================================================

class MessageResponse(BaseModel):
    """汎用メッセージレスポンス"""

    message: str
    job_id: int | None = None
