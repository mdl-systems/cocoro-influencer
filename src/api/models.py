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
    progress: int | None = None          # 進捗 0-100
    status_message: str | None = None    # 現在のステップ説明
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

class ScriptGenerateRequest(BaseModel):
    """台本生成リクエスト"""

    company_name: str = Field(..., min_length=1, description="会社名")
    product_name: str = Field(..., min_length=1, description="商品・サービス名")
    target_audience: str = Field(
        "20代〜40代のビジネスパーソン",
        description="ターゲット層",
    )
    tone: str = Field(
        "プロフェッショナルで親しみやすい",
        description="トーン・スタイル",
    )
    duration: str = Field("60秒", description="動画の長さ")
    provider: str = Field(
        "ollama",
        description="LLMプロバイダー (ollama / openai / gemini / anthropic)",
    )


class ScriptScene(BaseModel):
    """台本シーン (生成レスポンス用)"""

    scene_id: str
    text: str
    scene_type: str = "talking_head"
    pose: str = "neutral"
    camera_angle: str = "upper_body"
    cinematic_prompt: str = ""


class ScriptGenerateResponse(BaseModel):
    """台本生成レスポンス"""

    company_name: str
    product_name: str
    scenes: list[ScriptScene]
    raw: dict  # ScriptEngineの生出力 (デバッグ用)


class PipelineRunRequest(BaseModel):
    """フルパイプライン実行リクエスト"""

    customer_name: str = Field(..., min_length=1, description="顧客名")
    avatar_prompt: str | None = Field(
        None,
        description="アバタープロンプト (Noneまたは空文字の場合は既存のavatar.pngを使用)",
    )
    script: list[dict] = Field(..., min_length=1, description="台本 [{text, scene_type, caption}]")
    lora_path: str | None = Field(None, description="LoRAパス")
    output_format: str = Field("shorts", description="出力フォーマット")
    avatar_seed: int | None = Field(None, description="アバター生成シード")
    # ① 字幕自動生成
    enable_subtitles: bool = Field(False, description="台本テキストから字幕を自動生成する")
    # ② BGM
    bgm_name: str | None = Field(None, description="BGMファイル名 (/data/bgm/から選択)")
    bgm_volume: float = Field(0.12, ge=0.0, le=1.0, description="BGM音量 (0.0〜1.0)")
    # ③ 音声キャラクター
    model_id: int = Field(0, ge=0, description="Style-Bert-VITS2 モデルID")
    speaker_id: int = Field(0, ge=0, description="Style-Bert-VITS2 話者ID")
    # B-1 出力フォーマット (既存output_formatをUIから選択可能に)
    # B-2 トランジション
    transition: str = Field("none", description="シーン間トランジション (none/fade/wipeleft/wiperight/dissolve/slideleft)")
    transition_duration: float = Field(0.5, ge=0.0, le=2.0, description="トランジション時間 (秒)")
    # B-3 ウォーターマーク
    watermark_name: str | None = Field(None, description="ロゴファイル名 (/data/logos/から選択)")
    watermark_position: str = Field("bottom-right", description="ウォーターマーク位置")
    watermark_scale: float = Field(0.15, ge=0.05, le=0.5, description="ウォーターマークサイズ比率")


# =============================================================================
# 共通レスポンス
# =============================================================================

class MessageResponse(BaseModel):
    """汎用メッセージレスポンス"""

    message: str
    job_id: int | None = None
